"""认证服务（设计见 docs/OIDC_AUTH_DESIGN.md）。

两种模式（AUTH_MODE）：
- password：本地密码登录（默认）——scrypt 哈希验证，无外部依赖；
  OIDC 代码保留，AUTH_MODE=oidc 可随时切换（需已部署 Burrow）
- oidc：Authorization Code + PKCE S256 接入 Burrow

职责：require_auth 守卫、登录验证、会话 payload 管理、fail-fast 配置校验。
无 DB、无服务端状态。会话语义（SessionMiddleware，itsdangerous 内容签名 cookie）：
- 登录后 payload 键：sub / username / auth_time / amr
- 绝对超时由 SessionMiddleware max_age 承担（签名时间戳超龄 = 会话清空）
"""
import base64
import hashlib
import hmac
import secrets
import time
from typing import Optional, Tuple
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx2
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.oidc.core import IDToken
from fastapi import HTTPException, Request

from app.core.config import settings

# authlib 1.8 起 authlib.jose 为兼容层（2.0 移除），此处钉住 RS256 单算法


class AuthConfigError(RuntimeError):
    """AUTH_ENABLED=true 但配置缺失/非法——启动即失败，避免带病上线。"""


class OidcError(RuntimeError):
    """OIDC 流程错误（discovery / 换码 / 验签失败），callback 统一转 401。"""


def validate_auth_settings() -> None:
    if not settings.AUTH_ENABLED:
        return
    mode = settings.AUTH_MODE
    if mode not in ("password", "oidc"):
        raise AuthConfigError(f"AUTH_MODE 必须是 password 或 oidc（当前: {mode}）")
    if len(settings.AUTH_SECRET_KEY.encode()) < 32:
        raise AuthConfigError("AUTH_SECRET_KEY 至少 32 字节（openssl rand -base64 32）")
    if mode == "password":
        if not settings.AUTH_PASSWORD_HASH:
            raise AuthConfigError(
                "AUTH_MODE=password 需要 AUTH_PASSWORD_HASH（backend/scripts/hash_password.py 生成）")
        if not _valid_hash_format(settings.AUTH_PASSWORD_HASH):
            raise AuthConfigError("AUTH_PASSWORD_HASH 格式非法（用 scripts/hash_password.py 重新生成）")
        return
    missing = [
        name
        for name in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
                     "OIDC_REDIRECT_URI", "AUTH_ALLOWED_SUB")
        if not getattr(settings, name)
    ]
    if missing:
        raise AuthConfigError(f"AUTH_MODE=oidc 但缺少必填配置: {', '.join(missing)}")
    for name in ("OIDC_ISSUER", "OIDC_REDIRECT_URI"):
        if not getattr(settings, name).startswith(("http://", "https://")):
            raise AuthConfigError(f"{name} 必须是完整 http(s) URL")


# ===== password 模式：scrypt 哈希 =====
# 格式 scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>；stdlib 实现，零新依赖

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def _valid_hash_format(stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        return (
            scheme == "scrypt"
            and int(n) > 0 and int(r) > 0 and int(p) > 0
            and len(salt_hex) > 0 and len(hash_hex) > 0
        )
    except (ValueError, TypeError):
        return False


def resolve_cookie_secure() -> bool:
    value = (settings.COOKIE_SECURE or "auto").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    # auto：按登记回调地址协议推导——https 部署自动带 Secure，本地 http 冒烟不带
    return settings.OIDC_REDIRECT_URI.startswith("https://")


def sanitize_next(raw: Optional[str]) -> str:
    """登录回跳目标只放行站内相对路径，杜绝开放重定向（绝对 URL / //host / 反斜杠变体）。"""
    if not raw:
        return "/"
    if not raw.startswith("/"):
        return "/"
    if raw.startswith("//"):
        return "/"
    if "\\" in raw or any(ord(c) < 0x20 for c in raw):
        return "/"
    return raw


def require_auth(request: Request) -> None:
    """业务路由守卫：AUTH_ENABLED=false 时 no-op（存量测试与直调路由不受影响）。

    会话绝对超时已由 SessionMiddleware max_age 保证。oidc 模式额外比对 sub，
    使 AUTH_ALLOWED_SUB 收紧即刻吊销不匹配的存量会话（纵深防御）。
    """
    if not settings.AUTH_ENABLED:
        return
    sub = request.session.get("sub")
    if settings.AUTH_MODE == "oidc":
        if not sub or not secrets.compare_digest(str(sub), settings.AUTH_ALLOWED_SUB):
            raise HTTPException(status_code=401, detail="未登录或会话已过期")
    elif not sub:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")


_HTTP: Optional[httpx2.Client] = None


def _http() -> httpx2.Client:
    # 测试经 monkeypatch 注入 MockTransport 客户端拦截 discovery/token/JWKS。
    # trust_env=False：Burrow 属本机/内网直连，不走用户 shell 的代理环境变量
    global _HTTP
    if _HTTP is None:
        _HTTP = httpx2.Client(timeout=5.0, trust_env=False)
    return _HTTP


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def discover_oidc_metadata() -> dict:
    url = settings.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = _http().get(url)
    except httpx2.HTTPError as e:  # DNS/连接/超时等传输层异常统一收敛，杜绝 500
        raise OidcError(f"无法连接登录服务: {e}") from e
    if resp.status_code != 200:
        raise OidcError(f"Discovery 请求失败 (HTTP {resp.status_code})")
    try:
        meta = resp.json()
    except ValueError as e:
        raise OidcError("Discovery 响应不是合法 JSON") from e
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not meta.get(field):
            raise OidcError(f"Discovery 响应缺少 {field}")
    return meta


def build_authorize_url(meta: dict, state: str, nonce: str, verifier: str) -> str:
    query = urlencode({
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": _pkce_s256(verifier),
        "code_challenge_method": "S256",
    })
    return f"{meta['authorization_endpoint']}?{query}"


def begin_login_session(request: Request, next_path: str) -> Tuple[str, str, str]:
    """生成 state/nonce/verifier 写入预签发会话（各 256-bit 熵）。

    无论此前会话处于什么状态，一律 clear 后重建——预签发会话与任何旧会话互不继承。
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)  # RFC 7636 要求 43~128 字符
    session = request.session
    session.clear()
    session["auth_state"] = state
    session["auth_nonce"] = nonce
    session["auth_verifier"] = verifier
    session["auth_next"] = sanitize_next(next_path)
    session["auth_started_at"] = int(time.time())
    return state, nonce, verifier


def exchange_code_and_validate(meta: dict, code: str, verifier: str, nonce: str) -> dict:
    """换码 → 拉 JWKS → 验 ID Token（签名 / iss / aud / exp / iat / nonce），返回已校验 claims。"""
    try:
        resp = _http().post(
            meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.OIDC_REDIRECT_URI,
                "code_verifier": verifier,
            },
            auth=(settings.OIDC_CLIENT_ID, settings.OIDC_CLIENT_SECRET),
        )
    except httpx2.HTTPError as e:
        raise OidcError(f"换码请求失败: {e}") from e
    if resp.status_code != 200:
        raise OidcError(f"换码失败 (HTTP {resp.status_code})")
    try:
        id_token = resp.json().get("id_token")
    except ValueError as e:
        raise OidcError("Token 响应不是合法 JSON") from e
    if not id_token:
        raise OidcError("Token 响应缺少 id_token")

    try:
        jwks_resp = _http().get(meta["jwks_uri"])
    except httpx2.HTTPError as e:
        raise OidcError(f"JWKS 请求失败: {e}") from e
    if jwks_resp.status_code != 200:
        raise OidcError(f"JWKS 请求失败 (HTTP {jwks_resp.status_code})")
    try:
        # authlib/joserfc 的全部验签与 claims 异常在此收敛为 OidcError（callback 统一 401）
        key_set = JsonWebKey.import_key_set(jwks_resp.json())
        jwt_lib = JsonWebToken(["RS256"])  # 算法白名单，拒绝 alg 混淆/none
        claims = jwt_lib.decode(
            id_token,
            key_set,
            claims_cls=IDToken,
            claims_options={
                "iss": {"essential": True, "value": settings.OIDC_ISSUER},
                "aud": {"essential": True, "value": settings.OIDC_CLIENT_ID},
                "exp": {"essential": True},
                "iat": {"essential": True},
                "nonce": {"essential": True},
            },
            claims_params={"nonce": nonce},
        )
        claims.validate(leeway=30)
    except OidcError:
        raise
    except Exception as e:
        raise OidcError(f"ID Token 校验失败: {e}") from e
    return claims


def write_password_session(request: Request) -> None:
    """密码登录成功：写入会话（与 oidc 登录后的 payload 结构一致）。"""
    session = request.session
    session.clear()
    session["sub"] = "local"
    session["username"] = "本地账户"
    session["auth_time"] = int(time.time())
    session["amr"] = ["pwd"]


def write_auth_session(request: Request, claims: dict) -> None:
    """登录成功：清空预签发会话后写入新 payload（登录即轮转，预签发键绝不带入）。"""
    session = request.session
    session.clear()
    session["sub"] = str(claims["sub"])
    session["username"] = claims.get("preferred_username") or claims.get("email") or str(claims["sub"])
    session["auth_time"] = int(claims.get("auth_time") or time.time())
    amr = claims.get("amr")
    session["amr"] = amr if isinstance(amr, list) else ([] if amr is None else [str(amr)])


def build_end_session_url(meta: dict) -> Optional[str]:
    endpoint = meta.get("end_session_endpoint")
    if not endpoint:
        return None
    # 退出回跳 = 登记回调地址的站点根（与 Burrow 侧登记的退出回调精确匹配）
    parts = urlsplit(settings.OIDC_REDIRECT_URI)
    root = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
    return f"{endpoint}?{urlencode({'post_logout_redirect_uri': root})}"
