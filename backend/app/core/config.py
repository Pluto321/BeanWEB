import os
from pydantic_settings import BaseSettings

from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./beanweb.db"
    STORAGE_DIR: str = os.path.join(os.getcwd(), "storage", "raw")
    LEDGER_DIR: str = os.path.join(os.getcwd(), "ledgers")
    DEFAULT_ASSETS_ACCOUNT: str = "Assets:BeanWEB"
    DEFAULT_EXPENSES_ACCOUNT: str = "Expenses:Uncategorized"
    DEFAULT_INCOME_ACCOUNT: str = "Income:BeanWEB"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

settings = Settings()
