"""重导出（re-export）机制验证：SUPERSEDED + fragment 重生成 + 幂等。"""
import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.models import Base, Transaction, TransactionSplit, ExportRecord


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # 导出会写真实 ledgers 目录 → 重定向到临时目录
    monkeypatch.setattr("app.core.config.settings.LEDGER_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.export_service.settings.LEDGER_DIR", str(tmp_path))
    yield session
    session.close()


def _mk_txn(db, txn_id=None, amount="50.00", account="Expenses:Food"):
    txn = Transaction(
        id=txn_id, raw_transaction_id=None, date="2026-09-15",
        amount=amount, currency="CNY", merchant="测试商户",
        description="t", direction="支出", status="CONFIRMED",
    )
    db.add(txn)
    db.flush()
    db.add(TransactionSplit(transaction_id=txn.id, account=account, amount=amount, role="expense"))
    db.commit()
    return txn


def _fragment(session):
    from app.services.export_service import ExportService
    from app.services.ledger import LedgerManager
    from app.core.config import settings
    mgr = LedgerManager(settings.LEDGER_DIR)
    return os.path.join(mgr.generated_dir, "2026", "09.bean")


def test_reexport_replaces_fragment_content(db_session):
    """导出 → 编辑账户 → 重新确认 → 重导出：fragment 内容被替换，无重复分录"""
    from app.services.export_service import ExportService

    txn = _mk_txn(db_session, amount="50.00", account="Expenses:Food")
    ExportService.export_transaction(db_session, txn.id)
    db_session.commit()

    frag = _fragment(db_session)
    content = open(frag, encoding="utf-8").read()
    assert "Expenses:Food" in content
    assert content.count(f'id: "{txn.id}"') == 1

    # 模拟用户编辑账户分配（CONFIRMED → REVIEW_REQUIRED → CONFIRMED）
    db_session.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).delete()
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Expenses:Shopping", amount="50.00", role="expense"))
    txn.status = "REVIEW_REQUIRED"
    db_session.commit()
    txn.status = "CONFIRMED"
    db_session.commit()

    old_records = db_session.query(ExportRecord).filter(ExportRecord.transaction_id == txn.id).all()
    assert len(old_records) == 1 and old_records[0].status == "EXPORTED"
    old_record_id = old_records[0].id

    # 重导出
    rec = ExportService.reexport_transaction(db_session, txn.id)
    db_session.commit()

    # 旧记录 SUPERSEDED，新记录 EXPORTED
    assert rec.status == "EXPORTED"
    old_records = db_session.query(ExportRecord).filter(ExportRecord.transaction_id == txn.id).all()
    statuses = {r.id: r.status for r in old_records}
    assert statuses[old_record_id] == "SUPERSEDED"
    assert statuses[rec.id] == "EXPORTED"

    # fragment：新账户生效，旧账户消失，交易只出现一次
    content = open(frag, encoding="utf-8").read()
    assert "Expenses:Shopping" in content
    assert "Expenses:Food" not in content
    assert content.count(f'id: "{txn.id}"') == 1

    # 活跃记录唯一（下次重导出的前置判断依赖此不变量）
    active = db_session.query(ExportRecord).filter(
        ExportRecord.transaction_id == txn.id, ExportRecord.status == "EXPORTED"
    ).all()
    assert len(active) == 1


def test_reexport_requires_prior_export(db_session):
    """未导出过的交易不能重导出"""
    from app.services.export_service import ExportService
    txn = _mk_txn(db_session)
    with pytest.raises(ValueError, match="尚未导出"):
        ExportService.reexport_transaction(db_session, txn.id)


def test_reexport_requires_confirmed(db_session):
    """REVIEW_REQUIRED 状态不能重导出"""
    from app.services.export_service import ExportService
    txn = _mk_txn(db_session)
    ExportService.export_transaction(db_session, txn.id)
    db_session.commit()
    txn.status = "REVIEW_REQUIRED"
    db_session.commit()
    with pytest.raises(ValueError, match="CONFIRMED"):
        ExportService.reexport_transaction(db_session, txn.id)


def test_reexport_multiple_txns_same_month(db_session):
    """同月多笔交易：重导出其中一笔，另一笔分录保持且不重复"""
    from app.services.export_service import ExportService

    t1 = _mk_txn(db_session, amount="10.00", account="Expenses:A")
    t2 = _mk_txn(db_session, amount="20.00", account="Expenses:B")
    ExportService.export_transaction(db_session, t1.id)
    ExportService.export_transaction(db_session, t2.id)
    db_session.commit()

    # 编辑 t1
    db_session.query(TransactionSplit).filter(TransactionSplit.transaction_id == t1.id).delete()
    db_session.add(TransactionSplit(transaction_id=t1.id, account="Expenses:C", amount="10.00", role="expense"))
    t1.status = "REVIEW_REQUIRED"
    db_session.commit()
    t1.status = "CONFIRMED"
    db_session.commit()

    ExportService.reexport_transaction(db_session, t1.id)
    db_session.commit()

    frag = _fragment(db_session)
    content = open(frag, encoding="utf-8").read()
    # t1 新账户、t2 保留，各出现一次
    assert "Expenses:C" in content
    assert "Expenses:B" in content
    assert content.count(f'id: "{t1.id}"') == 1
    assert content.count(f'id: "{t2.id}"') == 1


def test_rewrite_month_fragment_idempotent(db_session):
    """fragment 重生成幂等：连续两次 rewrite 内容一致"""
    from app.services.export_service import ExportService
    from app.services.ledger import LedgerManager
    from app.core.config import settings

    txn = _mk_txn(db_session)
    ExportService.export_transaction(db_session, txn.id)
    db_session.commit()

    mgr = LedgerManager(settings.LEDGER_DIR)
    ExportService.rewrite_month_fragment(db_session, mgr, "2026", "09")
    c1 = open(_fragment(db_session), encoding="utf-8").read()
    ExportService.rewrite_month_fragment(db_session, mgr, "2026", "09")
    c2 = open(_fragment(db_session), encoding="utf-8").read()
    assert c1 == c2
    assert c2.count(f'id: "{txn.id}"') == 1
