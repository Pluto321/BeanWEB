"""Import 批次统计持久化（stats_json）验证。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.models import Base, ImportBatch


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_batch_stats_persisted(db_session):
    """analyze/commit 写入的统计应能持久化并读回（方案 A 核心）"""
    stats = {"total": 10, "created": 8, "existing": 2, "possible_duplicate": 0, "invalid": 0}
    batch = ImportBatch(source_type="ALIPAY", filename="t.csv", status="COMPLETED", stats_json=stats)
    db_session.add(batch)
    db_session.commit()

    row = db_session.query(ImportBatch).filter(ImportBatch.id == batch.id).first()
    assert row.stats_json == stats
    assert row.stats_json["created"] == 8
    assert row.stats_json["existing"] == 2


def test_batch_stats_nullable(db_session):
    """历史批次没有 stats 也能正常创建（nullable）"""
    batch = ImportBatch(source_type="BANK", filename="old.csv", status="COMPLETED")
    db_session.add(batch)
    db_session.commit()

    row = db_session.query(ImportBatch).filter(ImportBatch.id == batch.id).first()
    assert row.stats_json is None
