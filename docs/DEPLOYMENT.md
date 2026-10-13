# BeanWEB 生产部署（P2，形态 B）

关联：docs/OIDC_AUTH_DESIGN.md §2（拓扑）/ §12（认证模式决策）。
适用：单主机 + TLS 反代统一入口。**默认 `AUTH_MODE=password` 本地密码登录（零外部依赖）；
`AUTH_MODE=oidc` 接入 Burrow SSO（需另行部署 Burrow，见 §2）。**

## 1. 前提

- 本机已装：Python 3.13 venv（backend 依赖）、Node（构建前端）、Caddy 或 nginx
- 域名解析就绪；`oidc` 模式额外要求 Burrow 已部署（HTTPS issuer）

## 2. Burrow 注册清单（仅 `AUTH_MODE=oidc` 需要）

1. 创建应用：类型 **web**（confidential client）
   - 回调：`https://beanweb.example.com/api/auth/callback`（精确匹配）
   - 退出回调：`https://beanweb.example.com/`（精确匹配）
   - **不开 `allowWithoutPkce`**（Burrow 默认强制 PKCE S256）
   - 记下生成的 clientId / clientSecret（secret 仅显示一次）
2. 授权：把 `app:<应用ID>:login` 权限授予本人用户/用户组
3. （可选增强）全局开 `BURROW_MFA_ENABLED=true`
4. 查询本人 `sub` 填入 `AUTH_ALLOWED_SUB`

## 3. 构建与配置

```bash
# 前端（仓库根）
cd frontend && npm run build        # 产出 frontend/dist/

# 后端依赖（仓库根，已有 venv 跳过）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Linux: .venv/bin/pip
```

后端环境变量统一放**仓库根 `.env`**（systemd `EnvironmentFile` 加载；模板见
`deploy/env.example`，`.env` 已 gitignore、权限 600——`deploy/install.sh` 自动处理）：

| 变量 | 必填 | 说明 |
|---|---|---|
| `AUTH_ENABLED` | ✓ | `true`；缺必填项启动即失败（fail-fast） |
| `AUTH_MODE` | 可选 | `password`（默认，本地密码登录）/ `oidc`（Burrow SSO） |
| `AUTH_PASSWORD_HASH` | password 模式 | scrypt 哈希；生成：`cd backend && ../.venv/bin/python scripts/hash_password.py`（明文密码不落任何文件） |
| `AUTH_SECRET_KEY` | ✓ | 会话签名密钥，`openssl rand -base64 32`；**只进 env，绝不入 git** |
| `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` / `OIDC_REDIRECT_URI` / `AUTH_ALLOWED_SUB` | oidc 模式 | 见 §2 |
| `AUTH_SESSION_MAX_AGE` | 可选 | 默认 43200（12h 绝对超时，不滑动） |
| `COOKIE_SECURE` | 可选 | 默认 `auto`：按 `OIDC_REDIRECT_URI` 协议推导 |

`FRONTEND_DIST_DIR` 默认 `../frontend/dist`（相对 backend/），目录存在即自动同端口 serve。

## 4. 启动（systemd --user 单元，一键）

```bash
bash deploy/install.sh
```

脚本幂等，每次执行：从模板创建 `.env`（若缺）→ 生成
`~/.config/systemd/user/beanweb.service` → `daemon-reload` + `restart` →
尝试开启 linger → 探活验收并报告 auth 模式。**改完 `.env` 后重跑脚本即生效。**

生成的单元（等价手工形态，供参考）：

```ini
[Service]
WorkingDirectory=<仓库>/backend
EnvironmentFile=<仓库>/.env
ExecStart=<仓库>/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
```

- `--proxy-headers` + `--forwarded-allow-ips`：仅信任本机反代的 `X-Forwarded-Proto`，
  防外部伪造（设计 §6 契约）
- 绑定 `127.0.0.1`：应用端口不对外暴露，TLS 入口统一走反代
- `DATABASE_URL` 无需设置：代码默认已解析为 `<仓库>/backend/beanweb.db` 绝对路径
- **linger 必须开启**（user 级服务默认随 SSH 登出被回收）：
  `sudo loginctl enable-linger <user>`，脚本会尝试自动处理
- 启用登录：编辑 `.env`（`AUTH_ENABLED=true` + 六项真实值）→ 重跑 `install.sh`
  → 验收输出 `mode=oidc` 即生效；缺项时 fail-fast，`journalctl --user -u beanweb -n 20`
  会点名缺失变量

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

## 6. 上线冒烟清单（password 模式）

- [ ] `AUTH_ENABLED=false` 先启动：`/health` ok、浏览器打开 `/` 出现 UI（无登录门）
- [ ] 生成密码哈希（§3）+ 配全 `.env`（`AUTH_ENABLED=true` + `AUTH_MODE=password` + 两项）→ 重跑 `install.sh`：fail-fast 通过、验收 `mode=password`
- [ ] 浏览器访问 `https://beanweb.example.com/` → 登录门为密码表单 → 输错密码提示「密码错误」→ 输对进入应用
- [ ] 刷新页面会话保持；DevTools 查看 `Set-Cookie`：`HttpOnly` + `SameSite=Lax` + `Secure` + `Max-Age=43200`
- [ ] 「退出登录」→ 回到登录门 → 再访问要求重新登录
- [ ] （oidc 模式时另按 §2 注册 Burrow，登录门显示 SSO 入口；冒烟项同上）

## 7. 运维注意

- **`AUTH_SECRET_KEY` 泄露 = 全部会话可伪造**；轮换密钥即强制重新登录
- **改密码**：重跑 `scripts/hash_password.py` 生成新哈希替换 `.env` 中的 `AUTH_PASSWORD_HASH` → 重跑 `install.sh`
- **吊销手段**：调小 `AUTH_SESSION_MAX_AGE` 即刻清空全部存量会话（签名时间戳超龄作废）
- **已知边界（设计已接受）**：会话无服务端状态——登出仅指浏览器删除 cookie，
  cookie 值被复制重放在 12h 内仍有效；需强制下线时用上述吊销手段
- 登录审计写入本地 `audit_logs`（`entity_type=auth`、`action=LOGIN`），属运行时数据
- 备份流程不变：`POST /api/backups`（SQLite 在线快照到 `backend/backups/`）
- dev 工作流（vite 5173 → `/api` 代理 8000）与现状完全一致，dist serve 不影响
