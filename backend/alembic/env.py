import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# 确保 backend 目录在 sys.path 中，以便导入 app.models
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import Base, DATABASE_URL
from app.models.models import *

config = context.config
# 强制使用与运行时一致的数据库路径（绝对路径），避免 alembic.ini 相对路径在
# 非 backend 目录执行时建错库
config.set_main_option("sqlalchemy.url", DATABASE_URL)
# fileConfig(config.config_file_name)
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
