from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# DATABASE_URL 来自 settings（config.py 默认指向 backend/beanweb.db，
# 可用环境变量 DATABASE_URL 覆盖——测试/E2E 以此隔离数据库，绝不触碰真实账本）
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
