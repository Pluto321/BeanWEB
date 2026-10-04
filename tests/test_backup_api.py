"""备份 API 测试：backup_service 快照 + /api/backups 路由。

直调模式（项目惯例）：不启 TestClient，直接调路由函数/service；
settings.DATABASE_URL / BACKUP_DIR monkeypatch 到 tmp_path，绝不触碰生产库。
"""
import os
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.misc import create_backup as create_backup_route
from app.core.config import settings
from app.models.models import AuditLog, Base, Transaction
from app.services import backup_service


@pytest.fixture
def file_db(tmp_path, monkeypatch):
    """文件型临时库 + 临时 BACKUP_DIR；返回绑定该库的 session"""
    db_path = tmp_path / "beanweb_test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path / "backups"))
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def test_create_backup_snapshots_db(file_db):
    file_db.add(Transaction(date="2026-01-01", amount="12.34", merchant="商户A", status="REVIEW_REQUIRED"))
    file_db.commit()

    info = backup_service.create_backup(file_db)
    file_db.commit()

    assert info["file"].startswith("beanweb_") and info["file"].endswith(".db")
    dest = os.path.join(settings.BACKUP_DIR, info["file"])
    assert os.path.exists(dest) and info["size_bytes"] > 0

    # 快照可打开且含源库已提交数据；快照不含本次备份自身的审计行（先快照后记账）
    con = sqlite3.connect(dest)
    merchants = [r[0] for r in con.execute("select merchant from transactions")]
    audits = con.execute("select count(*) from audit_logs").fetchone()[0]
    con.close()
    assert merchants == ["商户A"]
    assert audits == 0

    # 审计日志写入源库（caller 已 commit）
    assert file_db.query(AuditLog).count() == 1


def test_list_backups_newest_first_and_filters(file_db, tmp_path):
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    for name in ["beanweb_20260101_000000.db", "beanweb_20260102_000000.db"]:
        open(os.path.join(settings.BACKUP_DIR, name), "wb").write(b"x" * 10)
    open(os.path.join(settings.BACKUP_DIR, "notes.txt"), "w").write("ignore")
    open(os.path.join(settings.BACKUP_DIR, "other.db"), "wb").write(b"x")

    items = backup_service.list_backups()
    assert [i["file"] for i in items] == ["beanweb_20260102_000000.db", "beanweb_20260101_000000.db"]
    assert all(set(i) == {"file", "size_bytes", "created_at"} for i in items)


def test_create_backup_rejects_memory_db(file_db, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(ValueError, match="SQLite 文件库"):
        backup_service.create_backup(file_db)


def test_create_backup_rejects_missing_file(file_db, tmp_path, monkeypatch):
    missing = tmp_path / "missing.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{missing}")
    with pytest.raises(ValueError, match="数据库文件不存在"):
        backup_service.create_backup(file_db)


def test_route_returns_success_and_commits(file_db):
    info = create_backup_route(db=file_db)
    assert info["status"] == "success"
    assert "file" in info and "size_bytes" in info
    # 路由已 commit：新 session 可见审计日志
    engine = create_engine(settings.DATABASE_URL)
    with sessionmaker(bind=engine)() as s:
        assert s.query(AuditLog).count() == 1
    engine.dispose()


def test_route_maps_value_error_to_400(file_db, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(HTTPException) as exc:
        create_backup_route(db=file_db)
    assert exc.value.status_code == 400


def test_list_backups_empty_when_dir_missing(file_db, tmp_path):
    assert backup_service.list_backups() == []
