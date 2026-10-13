"""认证端点（契约见 docs/OIDC_AUTH_DESIGN.md §4）。

- AUTH_ENABLED=false：login/callback 404，logout 幂等 no-op，me 返回 mode=disabled
- password 模式：POST /api/auth/login 验 scrypt 哈希签会话；错误 401
- oidc 模式：GET /api/auth/login 发起 OIDC；callback 任何失败 401 带 reason + 清空会话
- logout：本地会话是唯一事实源（无条件清除、不挂 require_auth）；
  仅 oidc 模式尝试构建 end_session_url，构不出来返回 null = 仅本地登出
"""
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.auth_service import (
    OidcError,
    begin_login_session,
    build_authorize_url,
    build_end_session_url,
    discover_oidc_metadata,
    exchange_code_and_validate,
    sanitize_next,
    verify_password,
    write_auth_session,
    write_password_session,
)
from app.services.review import AuditService

router = APIRouter(prefix="/api/auth")


class PasswordLoginBody(BaseModel):
    password: str


@router.post("/login")
def login_with_password(
    request: Request,
    body: PasswordLoginBody,
    db: Session = Depends(get_db),
):
    """password 模式：验密码哈希 → 签发会话（登录即轮转，防会话固定）。"""
    if not settings.AUTH_ENABLED or settings.AUTH_MODE != "password":
        raise HTTPException(status_code=404, detail="认证未启用或非密码模式")
    if not body or not verify_password(body.password, settings.AUTH_PASSWORD_HASH):
        time.sleep(0.3)  # 轻微延迟 + scrypt 本身的算力成本，抑制在线爆破
        raise HTTPException(status_code=401, detail="密码错误")
    write_password_session(request)
    AuditService.log_change(
        db, "auth", 0, "LOGIN", None,
        {"mode": "password", "username": "本地账户"},
        note="密码登录",
    )
    db.commit()  # auth 全在 API 层，事务由 caller 控制（核心原则 6）
    return {"authenticated": True, "username": "本地账户"}


@router.get("/login")
def login(request: Request, next: str = "/"):
    if not settings.AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="认证未启用")
    if settings.AUTH_MODE != "oidc":
        raise HTTPException(status_code=404, detail="非 oidc 模式，请使用 POST 登录")
    state, nonce, verifier = begin_login_session(request, next)
    try:
        meta = discover_oidc_metadata()
    except OidcError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return RedirectResponse(build_authorize_url(meta, state, nonce, verifier), status_code=302)


@router.get("/callback")
def callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = "",
    state: str = "",
    error: str = "",
):
    if not settings.AUTH_ENABLED or settings.AUTH_MODE != "oidc":
        raise HTTPException(status_code=404, detail="认证未启用或非 oidc 模式")
    session = request.session

    def fail(reason: str):
        session.clear()  # 成败均清空预签发会话（单次消费，不可重放）
        raise HTTPException(status_code=401, detail=reason)

    if error:
        fail(f"登录被拒绝: {error}")
    pre_state = session.get("auth_state")
    pre_nonce = session.get("auth_nonce")
    pre_verifier = session.get("auth_verifier")
    pre_next = session.get("auth_next")
    started_at = session.get("auth_started_at")
    if not (pre_state and pre_nonce and pre_verifier and pre_next and started_at):
        fail("登录状态缺失或已被使用，请重新发起登录")
    if not code or not state:
        fail("回调参数缺失")
    if time.time() - started_at > settings.AUTH_REQUEST_TTL:
        fail("登录请求已过期，请重新登录")
    if not secrets.compare_digest(state, pre_state):
        fail("state 校验失败")
    try:
        meta = discover_oidc_metadata()
        claims = exchange_code_and_validate(meta, code, pre_verifier, pre_nonce)
    except OidcError as e:
        fail(f"登录失败: {e}")
    if not secrets.compare_digest(str(claims.get("sub", "")), settings.AUTH_ALLOWED_SUB):
        fail("当前账号无权访问本应用")
    write_auth_session(request, claims)
    AuditService.log_change(
        db, "auth", 0, "LOGIN", None,
        {"sub": str(claims["sub"]), "username": request.session["username"]},
        note="OIDC 登录",
    )
    db.commit()  # auth 全在 API 层，事务由 caller 控制（核心原则 6）
    return RedirectResponse(sanitize_next(pre_next), status_code=302)


@router.get("/me")
def me(request: Request):
    if not settings.AUTH_ENABLED:
        return {"authenticated": False, "mode": "disabled",
                "username": None, "auth_time": None, "amr": None}
    mode = settings.AUTH_MODE
    sub = request.session.get("sub")
    if mode == "oidc":
        ok = bool(sub) and secrets.compare_digest(str(sub), settings.AUTH_ALLOWED_SUB)
    else:
        ok = bool(sub)
    if ok:
        return {"authenticated": True, "mode": mode,
                "username": request.session.get("username"),
                "auth_time": request.session.get("auth_time"),
                "amr": request.session.get("amr")}
    return {"authenticated": False, "mode": mode,
            "username": None, "auth_time": None, "amr": None}


@router.post("/logout")
def logout(request: Request):
    if not settings.AUTH_ENABLED:
        # off 模式未挂 SessionMiddleware，不能触碰 request.session——幂等 no-op
        return {"end_session_url": None}
    # 本地会话是唯一事实源：无条件清除（幂等），本端点不挂 require_auth——登出永远可用
    request.session.clear()
    if settings.AUTH_MODE != "oidc":
        return {"end_session_url": None}  # password 模式无 SSO 会话可撤销
    try:
        meta = discover_oidc_metadata()
    except OidcError:
        return {"end_session_url": None}  # SSO 撤销尽力而为，失败仅本地登出
    return {"end_session_url": build_end_session_url(meta)}
