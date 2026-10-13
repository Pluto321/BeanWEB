import os
from typing import List

from pydantic_settings import BaseSettings

# 默认指向 backend/beanweb.db（与既有部署一致）；可被环境变量 DATABASE_URL 覆盖，
# 测试/E2E 用它指向隔离数据库，绝不触碰真实账本
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'beanweb.db')}"


class Settings(BaseSettings):
    DATABASE_URL: str = DEFAULT_DATABASE_URL
    STORAGE_DIR: str = os.path.join(os.getcwd(), "storage", "raw")
    LEDGER_DIR: str = os.path.join(os.getcwd(), "ledgers")
    BACKUP_DIR: str = os.path.join(os.getcwd(), "backups")
    DEFAULT_ASSETS_ACCOUNT: str = "Assets:BeanWEB"
    DEFAULT_EXPENSES_ACCOUNT: str = "Expenses:Uncategorized"
    DEFAULT_INCOME_ACCOUNT: str = "Income:BeanWEB"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ===== 认证（设计见 docs/OIDC_AUTH_DESIGN.md；AUTH_ENABLED=false 时全部 no-op）=====
    # AUTH_MODE=password：本地密码登录（默认，无外部依赖；需 AUTH_PASSWORD_HASH）
    # AUTH_MODE=oidc：接入 Burrow SSO（需已部署 Burrow，六项 OIDC 配置 fail-fast）
    AUTH_ENABLED: bool = False
    AUTH_MODE: str = "password"
    AUTH_PASSWORD_HASH: str = ""     # password 模式必填；scripts/hash_password.py 生成（scrypt）
    OIDC_ISSUER: str = ""            # oidc 模式：如 https://sso.example.com（与 Burrow 侧登记一致）
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""      # 如 https://beanweb.example.com/api/auth/callback
    AUTH_ALLOWED_SUB: str = ""       # oidc 模式必填：绑定唯一 Burrow 用户 sub
    AUTH_SECRET_KEY: str = ""        # 会话签名密钥（≥32 随机字节），只进 env 绝不入 git
    AUTH_SESSION_MAX_AGE: int = 43200  # 会话绝对超时（秒），默认 12h，不滑动
    AUTH_REQUEST_TTL: int = 600        # 预签发登录请求有效期（秒）
    COOKIE_SECURE: str = "auto"      # auto|true|false；auto 按 OIDC_REDIRECT_URI 协议推导

    # 生产（形态 B）：uvicorn 同端口 serve 前端构建产物；目录不存在则自动跳过，
    # dev 流程（vite 5173 → /api 代理）不受影响
    FRONTEND_DIST_DIR: str = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")

settings = Settings()
