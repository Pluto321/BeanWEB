# BeanWEB OIDC SSO 接入设计（Burrow 作为身份提供方）

状态：**P1 + P2 代码侧已完成（2026-10-11）：后端 + 前端 + dist serve/SPA fallback + 部署文档
（docs/DEPLOYMENT.md）；off 模式零扰动（87 存量测试全绿）；§7 mock 测试按用户决定延后；
剩余：Burrow 侧注册 + 真实联调冒烟（见 DEPLOYMENT.md §2/§6）**
日期：2026-10-10（定稿）/ 2026-10-11（补齐 + P1/P2 实现）
关联：HANDOFF.md 核心原则 7/8；gap #4（requirements 分层）

## 1. 背景与目标

BeanWEB 目前是**零鉴权**的单用户本地应用（uvicorn 绑定 localhost，前端 5173 dev proxy）。
用户自建了 [Burrow](https://github.com/ArkGravity/burrow)（轻量 OIDC 单点登录服务）管理
Grafana/Nightingale 等自托管应用，希望 BeanWEB 以 OIDC 客户端身份接入，获得统一登录。

**目标**
- BeanWEB 全部 API 与 UI 受 OIDC 登录保护（可配置开关，默认关闭）
- 登录/授权/会话复用 Burrow，BeanWEB 不自建用户体系、不存密码
- 本地开发（`AUTH_ENABLED=false`）零影响：现有 87 个测试与日常流程原样可用

**非目标**
- 不做多用户/权限细分——BeanWEB 仍是单用户应用，登录资格由 Burrow 侧权限控制
- 不做 Authorization Code 之外的流程（implicit/密码/refresh 均不用；Burrow 也不发 refresh token）
- 不把 Burrow 的 ID/Access Token 当作 API 令牌——只在后端换码时校验一次，之后用 BeanWEB 自签会话

## 2. 部署形态与威胁模型

| 形态 | 说明 | 鉴权必要性 |
|---|---|---|
| A. 纯 localhost（现状） | uvicorn 127.0.0.1:8000 | SSO 无安全增益，`AUTH_ENABLED=false` 保持 |
| B. 局域网/公网（目标形态） | 服务器部署，TLS 反代统一入口 | **auth + HTTPS 必须**——库存放全部个人财务明细 |

形态 B 拓扑（单主机）：

```
浏览器 ──HTTPS──> 反代（Caddy/nginx）
                   ├─ beanweb.example.com/        → uvicorn（serve 前端 dist + /api）
                   └─ sso.example.com/            → Burrow（→ PostgreSQL）
```

威胁模型：防未授权浏览器访问与跨站攻击；不防本机恶意进程、不防物理接触。
凭据集中：Burrow 管 MFA/TOTP，BeanWEB 只管自己的会话 cookie。

## 3. 认证流程

注册为 Burrow **Web 类型应用**（confidential client）：`client_secret_basic` + **PKCE S256 强制**
（Burrow 默认，勿开 `allowWithoutPkce`）。Scopes：`openid profile email`（不请求 phone）。

```
浏览器                     BeanWEB 后端                          Burrow (IdP)
  │ GET /api/auth/login?next=/x      │                                │
  │────────────────────────────────>│ 生成 state/nonce/PKCE verifier │
  │                                  │ 存入会话 cookie（预签发）      │
  │<──302 authorize──────────────────│───────────────────────────────>│ 登录（密码/TOTP）
  │                                                                                │
  │ GET /api/auth/callback?code&state  │                                │
  │────────────────────────────────>│ 校验 state                     │
  │                                   │ POST token（basic auth + verifier）
  │                                   │<──id_token / access_token──────│
  │                                   │ JWKS 验签 + iss/aud/exp/nonce   │
  │                                   │ 签发 BeanWEB 会话（HttpOnly cookie）
  │<──302 next（仅允许相对路径）──────│                                │
```

ID Token 校验清单（authlib `oidc` 模块托管）：签名（Discovery 拉 JWKS）、`iss==OIDC_ISSUER`、
`aud==client_id`、`exp/iat`（leeway 30s）、`nonce` 与预签发会话匹配。成功后只取
`sub` / `preferred_username` / `email`，不落库存 token。

**会话生命周期**：BeanWEB 会话独立于 Burrow 会话，有效期 `AUTH_SESSION_MAX_AGE`（默认 12h，
绝对超时不滑动）。到期后重新走 authorize——若 Burrow 浏览器会话仍有效则无感跳回；若被撤销
（改密/MFA 重置）则需重新登录。Burrow 明确不控制 APP 会话，此边界与官方文档一致。

**登出（全局，语义分级与失败处理）**：
- **本地会话是唯一事实源**：`POST /api/auth/logout` 无条件清除 `beanweb_session`
  （幂等，会话已过期/不存在也 200）；该端点**不挂 require_auth**——登出永远必须可用。
- **SSO 会话撤销为尽力而为**：清除成功后返回 `{end_session_url}`（Burrow Discovery 的
  `end_session_endpoint` + `post_logout_redirect_uri`，与 Burrow 侧登记精确匹配），前端
  **顶层整页跳转**，Burrow 撤销自身会话后回跳应用根路径。
- **失败降级**：Discovery 无 `end_session_endpoint` / Burrow 不可达 → 返回
  `{end_session_url: null}`，前端视为**仅本地登出**，停留在登录门页，不做死链跳转；
  即使 end_session 跳转中途失败，本地会话已清除，无安全残留。
- **不携带 `id_token_hint`**（遵循「不存 Burrow Token」决策）；若 Burrow 由此弹确认页
  或将来要求 hint，P1 冒烟时按实测记录为开放项再议。

### 3.1 state / nonce / verifier 的存储与验证（预签发会话）

- **生成**：`/api/auth/login` 用 `secrets.token_urlsafe(32)` 独立生成 state、nonce、
  PKCE verifier（各 256-bit 熵），连同 `next` 与 `login_started_at` 写入**匿名预签发会话**
  （复用 `beanweb_session` cookie，itsdangerous 签名保证不可伪造，服务端零状态）。
- **有效期**：预签发 payload 自 `login_started_at` 起 **`AUTH_REQUEST_TTL`（默认 600s）**内
  有效，过期 callback 拒绝并清空会话——挂起的登录尝试不会长期存活。
- **callback 校验顺序**（任一步失败即 401 并**清空整个会话**）：
  1. 会话存在且含完整三元组（缺失 = 非本站发起 / 已被消费）
  2. 未超过 `AUTH_REQUEST_TTL`
  3. `state` 与 query 参数**常数时间比较**（`secrets.compare_digest`）一致
  4. 换码成功后 ID Token 的 `nonce` 与会话中一致（authlib 校验）
  verifier 不做本地比较，只随 code 送 token 端点（Burrow 侧校验 S256 challenge）。
- **单次使用**：callback 无论成败，预签发 payload 全部清除——成功轮转为登录后会话
  （见 3.2），失败整体清空；code 单次性由 Burrow 保证，同一 callback URL 无法重放。

### 3.2 会话固定（session fixation）防护

BeanWEB 会话是**服务端签名的内容 cookie**（itsdangerous），不是服务端会话表的随机 ID，
经典「攻击者预置会话 ID、受害者登录后沿用」没有落点。仍做双层防护：

1. **登录即轮转**：callback 成功后 `session.clear()` 再写入新 auth payload——
   state/nonce/verifier/next 被消费，绝不带入登录后会话；Set-Cookie 整体覆盖旧值。
2. **sub 绑定兜底**：即使攻击者诱导受害者完成攻击者发起的登录流，签出的会话
   `sub ≠ AUTH_ALLOWED_SUB` → 拒绝签发/`require_auth` 放行无门，会话不可用。

验收断言：登录后 cookie 中无任何预签发键；新 cookie 值 ≠ 旧值；重放 callback → 401。

## 4. API 契约（新增，均不落库、无 migration）

| 端点 | 方法 | 行为 |
|---|---|---|
| `/api/auth/login?next=` | GET | 生成 state/nonce/PKCE，302 到 Burrow authorize；`next` 只接受站内相对路径 |
| `/api/auth/callback` | GET | state 校验 → 换码 → 验 ID Token → 签会话 → 302 `next`；失败 401 带 reason |
| `/api/auth/me` | GET | `{authenticated, mode: "oidc"/"disabled", username, auth_time, amr}` |
| `/api/auth/logout` | POST | 清 cookie，返回 `{end_session_url}` |
| `/health` | GET | 保持公开（存活探针） |

**守卫**：`require_auth` 作为 FastAPI 依赖挂到现有 4 个业务 router
（`app.include_router(..., dependencies=[Depends(require_auth)])`，main.py:19-22）。
`AUTH_ENABLED=false` 时 `require_auth` 直接放行（no-op）→ 全部现有测试与直调路由不受影响。

## 5. 配置（config.py Settings，均可 env 覆盖）

```
AUTH_ENABLED=false            # 总开关；true 时下述六项必填，缺失 fail-fast 拒绝启动
OIDC_ISSUER=                  # 如 https://sso.example.com（注意与 Burrow 侧登记一致）
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=           # 16–256 位可打印 ASCII（Burrow 创建应用时生成，仅显示一次）
OIDC_REDIRECT_URI=            # 如 https://beanweb.example.com/api/auth/callback（精确匹配）
AUTH_ALLOWED_SUB=             # 必填：绑定唯一 Burrow 用户 sub（已定决策 #1），不匹配拒绝签发
AUTH_SECRET_KEY=              # 会话签名密钥，≥32 随机字节（openssl rand -base64 32）；
                              # 泄露=全部会话可伪造，只进 env/部署密钥，绝不入 git
AUTH_SESSION_MAX_AGE=43200     # 12h，绝对超时（调小即刻吊销全部存量会话，见 §6）
AUTH_REQUEST_TTL=600           # 预签发登录请求有效期（秒），state/nonce/verifier 超时作废
COOKIE_SECURE=auto             # auto|true|false；auto 按 OIDC_REDIRECT_URI 协议推导
```

## 6. 实现要点

**后端**（新增 `app/api/auth.py` + `app/services/auth_service.py`）
- 依赖（已入 requirements）：`authlib` 1.8（`authlib.oidc.core.IDToken` 托管验签；
  `authlib.jose` 为 1.8 兼容层，2.0 移除时迁 joserfc）、`httpx2`（httpx 后继版，
  starlette 1.6 TestClient 同源；OIDC 出站客户端 `trust_env=False`，
  不受 shell 代理变量劫持）、`itsdangerous`（Starlette `SessionMiddleware`
  签名 cookie）——无 Redis，原则 7 不破
- 会话：`SessionMiddleware` **仅在 `AUTH_ENABLED=true` 时挂载**（off 模式零中间件零扰动），
  参数 `secret_key=AUTH_SECRET_KEY, session_cookie="beanweb_session",
  max_age=AUTH_SESSION_MAX_AGE, same_site="lax", https_only=COOKIE_SECURE)`
  ——HttpOnly 恒开（Starlette 固定行为）；`max_age` 即绝对超时（签名时间戳超龄=会话清空，
  故调小配置即刻吊销全部存量会话，无需服务端黑名单）；payload：
  `{sub, username, auth_time, amr}`，无服务端状态
- **HTTPS / 反代契约（P2 落地，此处先定死）**：所有对外 URL（authorize 回调、
  logout 回跳）一律取自显式配置（`OIDC_ISSUER` / `OIDC_REDIRECT_URI`），
  **绝不从请求 Host/Referer 拼 URL**，杜绝 host-header 投毒类问题；生产 uvicorn 须以
  `--proxy-headers --forwarded-allow-ips=127.0.0.1` 运行（单机反代），反代透传
  `X-Forwarded-Proto: https`；`COOKIE_SECURE=auto` 下 https 形态自动带 Secure，
  本地 http 冒烟自动不带——同一套代码两种形态无需改配置
- 登录成功写一条审计：`AuditService.log_change(db, "auth", 0, "LOGIN", None, {sub, username}, ...)`
  （复用 audit_logs 表，无 migration）
- CSRF：同源 + SameSite=Lax + 纯 JSON API 已挡跨站表单，v1 不引入 CSRF token（单用户应用，记录为开放项）

**前端**
- `apiFetch`（client.ts）增加 401 拦截：保存当前路由 → 整页跳转 `/api/auth/login?next=...`
  （OIDC 回调必须顶层导航，不能 XHR）
- App 挂载时先 `GET /api/auth/me`：未认证（oidc 模式）→ 渲染「前往登录」占位页
- Sidebar 底部（auth on 时）加「退出登录」→ POST logout → 跳 `end_session_url`
- dev 模式（AUTH off）行为与现在完全一致

**Burrow 侧注册清单**（运维）
1. 创建应用：类型 **web**；回调 `https://beanweb.example.com/api/auth/callback`；
   退出回调 `https://beanweb.example.com/`；不开 `allowWithoutPkce`；记下 clientId/secret
2. 角色：把 `app:<应用ID>:login` 权限授给本人用户/用户组
3. `BURROW_ISSUER` 为 HTTPS 地址（Burrow 安装要求）
4. （可选增强）全局开 `BURROW_MFA_ENABLED=true`，让 BeanWEB 间接受 TOTP 保护

## 7. 测试策略

- **默认路径零扰动**：`AUTH_ENABLED=false` 下 `require_auth` no-op，87 个存量测试不改动
- 新增 `tests/test_auth.py`：
  - off 模式：`/api/auth/me` 返回 `mode=disabled`；业务端点可访问
  - on 模式（mock IdP）：httpx2 `MockTransport` 拦截 Discovery/JWKS/token 端点，
    `cryptography` 生成 RSA keypair 自签 ID Token；**测试用真实 `SessionMiddleware`
    签名链路**（测试专用 `AUTH_SECRET_KEY` 经 env 注入，不打桩）——覆盖：
    - 成功签发：Set-Cookie 含 HttpOnly + SameSite=Lax（https 配置时含 Secure），
      会话 payload 含 sub/username/auth_time/amr
    - state 不匹配 / 缺失 / 过期（`login_started_at` 超 `AUTH_REQUEST_TTL`）→ 401 且会话清空
    - nonce 不匹配（ID Token 用错 nonce）→ 401；JWKS 验签失败 → 401
    - `AUTH_ALLOWED_SUB` 不匹配 → 401
    - **真实签名攻击面**：篡改/伪造 cookie（含错误 key 的合法结构）→ 视为匿名 → 401
    - **会话过期**：用测试 key 合法签名一枚 `auth_time` 超过 `AUTH_SESSION_MAX_AGE`
      的会话 → require_auth 401、`/api/auth/me` 报未认证
    - **会话固定**：成功回调后新 cookie 不含 state/nonce/verifier 且值 ≠ 旧值；
      重放同一 callback URL → 401
    - **跨站 / 登录 CSRF**：受害者浏览器无会话时携带攻击者预签发 cookie 之外的
      state 回调 → 401（state 与会话绑定，SameSite=Lax 挡跨站携带）
    - `next` 开放重定向：绝对 URL / `//host` / 反斜杠变体 → 拒绝，仅放行站内相对路径
    - 登出：cookie 清除且返回 `end_session_url`；Burrow 无 `end_session_endpoint`
      → `end_session_url: null` 仍 200；disabled 模式 no-op
  - conftest 隔离不破：auth 测试不触碰业务表
- 冒烟（手工，记录步骤）：本地起 Burrow 单端口模式（`localhost:8080`）+ BeanWEB `AUTH_ENABLED=true`
  真实走一遍登录/登出

## 8. 阶段划分

| 阶段 | 内容 | 规模估计 |
|---|---|---|
| P1 核心接入 | 配置 + auth 端点 + require_auth + 会话 + apiFetch 401 + 前端门/登出 + mock 测试 | ~1 个工作日当量（**已完成 2026-10-11，mock 测试延后**） |
| P2 生产部署 | FastAPI StaticFiles serve 前端 dist + Caddy/nginx 样例 + Burrow 注册联调 + 部署文档 | ~0.5 天（**代码侧已完成 2026-10-11**：dist serve + SPA fallback + `--proxy-headers` 契约 + `docs/DEPLOYMENT.md`；**Burrow 注册联调待执行**，见 DEPLOYMENT.md §2/§6） |
| P3 可选增强 | 登录页显示 `auth_time/amr`、会话刷新策略、CSRF token（若开放更多端点） | 按需 |

## 9. 核心原则影响核对

| 原则 | 核对 |
|---|---|
| 7（不引入重中间件） | Burrow 是外部既有基础设施；BeanWEB 内部仍是单体；会话无服务端存储 ✓ |
| 6（Service 不 commit） | auth 全在 API 层，审计随请求提交 ✓ |
| 8（apiFetch 统一入口） | 401 拦截加在 apiFetch 内部，所有调用方自动受益 ✓ |
| 13/14（测试隔离/生产写授权） | 无 migration、无业务表写入；登录审计行属运行时数据，本地 DB 内 ✓ |
| 15（隐私） | username/email 只进本地 audit_logs，绝不进 git ✓ |

## 10. 已定决策（2026-10-10 用户拍板）

1. **AUTH_ALLOWED_SUB：绑定唯一 Burrow 用户 sub**——由可选改为**必填**
   （`AUTH_ENABLED=true` 时缺失即 fail-fast 拒绝启动），防将来在 Burrow 侧误授权他人
2. **会话时长：12h 绝对超时**（`AUTH_SESSION_MAX_AGE=43200`，不滑动）
3. **登出：全局登出**——清本地 cookie 并跳 Burrow `end_session`（带已登记的
   `post_logout_redirect_uri`），连 SSO 会话一起撤销
4. **实现时机：待用户审完设计后开工**；P2（HTTPS 反代 + StaticFiles + Burrow 注册联调）
   是否与 P1 同批做，取决于届时的局域网/公网部署计划

## 11. 开工前补齐决策（2026-10-11，对应 5 项预实现事项）

5. **state/nonce/verifier 存预签发会话 cookie**（服务端零状态）：各 256-bit 熵，
   `AUTH_REQUEST_TTL=600s` 内有效；callback 按序校验（存在性 → TTL → state 常数时间比对
   → nonce），任一步失败 401 并清空；成败均单次消费，不可重放（详见 §3.1）
6. **会话固定防护 = 登录即轮转 + `AUTH_ALLOWED_SUB` 兜底**：内容签名 cookie 无预置 ID
   落点；成功回调后预签发字段全清、cookie 值全新（详见 §3.2）
7. **Secure Cookie 与反代契约显式化**：新增 `AUTH_SECRET_KEY`（fail-fast 必填，会话签名
   密钥）与 `COOKIE_SECURE=auto`（按 `OIDC_REDIRECT_URI` 协议推导）；对外 URL 一律显式
   配置、不取请求头；uvicorn `--proxy-headers --forwarded-allow-ips` 契约写入 P2（详见 §6）
8. **登出语义分级**：本地会话=唯一事实源（幂等清除，logout 端点不挂 require_auth）；
   SSO 撤销=尽力而为（`end_session_url: null` 即仅本地登出，不死链跳转）；
   不携带 `id_token_hint`（详见 §3 登出段）
9. **auth 测试走真实签名链路**：不桩 SessionMiddleware，测试 key 经 env 注入；覆盖
   签名伪造、会话过期、固定轮转、跨站 state 绑定、开放重定向、登出降级（详见 §7）
