# BeanWEB 生产部署（P2，形态 B）

关联：docs/OIDC_AUTH_DESIGN.md §2（拓扑）/ §5（配置）/ §6（反代契约）。
适用：单主机 + TLS 反代统一入口；Burrow 与 BeanWEB 同机（异机同理，改反代目标即可）。

## 1. 前提

- Burrow 已部署，`BURROW_ISSUER` 为 HTTPS 地址（Burrow 安装要求）
- 本机已装：Python 3.13 venv（backend 依赖）、Node（构建前端）、Caddy 或 nginx
- 域名解析就绪：`beanweb.example.com` 与 `sso.example.com` 均指向本机

## 2. Burrow 侧注册（联调清单）

1. 创建应用：类型 **web**（confidential client）
   - 回调：`https://beanweb.example.com/api/auth/callback`（精确匹配）
   - 退出回调：`https://beanweb.example.com/`（精确匹配）
   - **不开 `allowWithoutPkce`**（Burrow 默认强制 PKCE S256）
   - 记下生成的 clientId / clientSecret（secret 仅显示一次）
2. 授权：把 `app:<应用ID>:login` 权限授予本人用户/用户组
3. （可选增强）全局开 `BURROW_MFA_ENABLED=true`，BeanWEB 间接受 TOTP 保护
4. 查询本人 `sub`（Burrow 用户详情/API），填入 `AUTH_ALLOWED_SUB`

## 3. 构建与配置

```bash
# 前端（仓库根）
cd frontend && npm run build        # 产出 frontend/dist/

# 后端依赖（仓库根，已有 venv 跳过）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Linux: .venv/bin/pip
```

后端环境变量（CWD=backend/）：

| 变量 | 必填 | 说明 |
|---|---|---|
| `AUTH_ENABLED` | ✓ | `true`；缺失任一必填项启动即失败（fail-fast） |
| `OIDC_ISSUER` | ✓ | 如 `https://sso.example.com`，与 Burrow 侧登记一致 |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | ✓ | Burrow 创建应用时生成 |
| `OIDC_REDIRECT_URI` | ✓ | `https://beanweb.example.com/api/auth/callback` |
| `AUTH_ALLOWED_SUB` | ✓ | 绑定唯一授权用户 sub，不匹配拒绝签发会话 |
| `AUTH_SECRET_KEY` | ✓ | 会话签名密钥，`openssl rand -base64 32`；**只进 env，绝不入 git** |
| `AUTH_SESSION_MAX_AGE` | 可选 | 默认 43200（12h 绝对超时，不滑动） |
| `AUTH_REQUEST_TTL` | 可选 | 默认 600（登录请求有效期秒） |
| `COOKIE_SECURE` | 可选 | 默认 `auto`：按 OIDC_REDIRECT_URI 协议自动推导，https 部署无需设置 |

`FRONTEND_DIST_DIR` 默认 `../frontend/dist`（相对 backend/），目录存在即自动同端口 serve。

## 4. 启动（uvicorn 契约）

```bash
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips=127.0.0.1
```

- `--proxy-headers` + `--forwarded-allow-ips`：仅信任本机反代的 `X-Forwarded-Proto`，
  防外部伪造（设计 §6 契约）
- 绑定 `127.0.0.1`：应用端口不对外暴露，TLS 入口统一走反代
- 进程管理：systemd / nssm / PM2 任选，注意 env 注入方式

## 5. 反代样例

Caddy（自动 HTTPS，推荐）：

```caddyfile
beanweb.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}

sso.example.com {
    reverse_proxy 127.0.0.1:8080   # Burrow，按实际端口
}
```

nginx（需自行配证书，如 certbot）：

```nginx
server {
    listen 443 ssl;
    server_name beanweb.example.com;
    ssl_certificate     /etc/letsencrypt/live/beanweb.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/beanweb.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 6. 上线冒烟清单

- [ ] `AUTH_ENABLED=false` 先启动：`/health` ok、浏览器打开 `/` 出现 UI（无登录门）
- [ ] 按 §2 完成 Burrow 注册，按 §3 配全 env 重启：fail-fast 通过
- [ ] 浏览器访问 `https://beanweb.example.com/` → 登录门 →「前往登录」→ Burrow 完成登录 → 回跳应用
- [ ] 刷新页面会话保持；DevTools 查看 `Set-Cookie`：`HttpOnly` + `SameSite=Lax` + `Secure` + `Max-Age=43200`
- [ ] 「退出登录」→ 跳 Burrow `end_session` → 回应用根路径 → 再访问要求登录
- [ ] （负向）Burrow 侧临时把 `app:<ID>:login` 授给一个测试用户 → 该用户登录被拒（`AUTH_ALLOWED_SUB` 兜底）→ 移除权限

## 7. 运维注意

- **`AUTH_SECRET_KEY` 泄露 = 全部会话可伪造**；轮换密钥即全员强制重新登录
- **吊销手段**：调小 `AUTH_SESSION_MAX_AGE` 即刻清空全部存量会话（签名时间戳超龄作废）；
  改 `AUTH_ALLOWED_SUB` 即刻拒绝其他用户
- **已知边界（设计已接受，威胁模型 §2）**：会话无服务端状态——登出仅指浏览器删除 cookie，
  cookie 值被复制重放在 12h 内仍有效；Burrow 侧改密/MFA 重置不影响已签发的 BeanWEB 会话，
  需等超时或用上述吊销手段强制下线
- 登录审计写入本地 `audit_logs`（`entity_type=auth`、`action=LOGIN`），属运行时数据
- 备份流程不变：`POST /api/backups`（SQLite 在线快照到 `backend/backups/`）
- dev 工作流（vite 5173 → `/api` 代理 8000）与现状完全一致，dist serve 不影响
