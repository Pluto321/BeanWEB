"""数据库备份：SQLite 在线快照到 BACKUP_DIR。

- 命名沿用既有手工备份惯例：beanweb_YYYYMMDD_HHMMSS.db
- 用 sqlite3 backup API 取一致快照（比文件复制安全，兼容被打开中的库）
- Service 层不 commit（原则 6），审计日志由 caller 提交
"""
import os
import sqlite3
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.review import AuditService


def resolve_db_path() -> str | None:
    """settings.DATABASE_URL → SQLite 文件绝对路径；非文件库（:memory:/非 sqlite）返回 None。"""
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path and path != ":memory:":
            return os.path.normpath(os.path.abspath(path))
    return None


def create_backup(db: Session) -> dict:
    """把当前数据库快照到 BACKUP_DIR，返回备份元数据。"""
    src = resolve_db_path()
    if src is None:
        raise ValueError("当前数据库不是 SQLite 文件库，无法备份")
    if not os.path.exists(src):
        raise ValueError(f"数据库文件不存在: {src}")

    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    name = f"beanweb_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest = os.path.join(settings.BACKUP_DIR, name)

    src_conn = sqlite3.connect(src)
    try:
        dest_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    AuditService.log_change(db, "backup", 0, "CREATE", None, {"file": name}, "Database backup")
    return {"file": name, "size_bytes": os.path.getsize(dest)}


def list_backups() -> list[dict]:
    """列出 BACKUP_DIR 下的 beanweb_*.db，新→旧排序。"""
    if not os.path.isdir(settings.BACKUP_DIR):
        return []
    items = []
    for fn in os.listdir(settings.BACKUP_DIR):
        if fn.startswith("beanweb_") and fn.endswith(".db"):
            path = os.path.join(settings.BACKUP_DIR, fn)
            items.append({
                "file": fn,
                "size_bytes": os.path.getsize(path),
                "created_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
            })
    items.sort(key=lambda x: x["file"], reverse=True)
    return items
