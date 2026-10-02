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
    DEFAULT_ASSETS_ACCOUNT: str = "Assets:BeanWEB"
    DEFAULT_EXPENSES_ACCOUNT: str = "Expenses:Uncategorized"
    DEFAULT_INCOME_ACCOUNT: str = "Income:BeanWEB"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

settings = Settings()
