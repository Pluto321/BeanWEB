"""规则存量重跑测试：RuleService.rerun_rules + POST /api/rules/apply。

语义：非 CONFIRMED 交易的支出分类腿按当前规则预填；收入跳过；
状态不变；dry_run 不落库；CONFIRMED 不覆盖（裁决权在人）。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.misc import apply_rules
from app.models.models import AuditLog, Base, Rule, Transaction, TransactionSplit
from app.services.rule_service import RuleService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _add_rule(db, name, pattern, account, priority=10):
    db.add(Rule(name=name, priority=priority, enabled=True))
    db.flush()
    rule = db.query(Rule).filter(Rule.name == name).first()
    from app.models.models import RuleCondition, RuleAction
    db.add(RuleCondition(rule_id=rule.id, key="merchant", pattern=pattern))
    db.add(RuleAction(rule_id=rule.id, action_type="account", value=account))


def _add_txn(db, merchant, direction="支出", status="REVIEW_REQUIRED", cat="Expenses:Uncategorized"):
    db.add(Transaction(
        date="2026-01-01", amount="10.00", merchant=merchant, description="",
        counterparty="", direction=direction, status=status,
    ))
    db.flush()
    txn = db.query(Transaction).order_by(Transaction.id.desc()).first()
    db.add(TransactionSplit(transaction_id=txn.id, account=cat, amount="10.00", role="expense"))
    db.add(TransactionSplit(transaction_id=txn.id, account="Assets:BeanWEB", amount="-10.00", role="payment"))
    return txn


def _expense_account(db, txn_id):
    return (
        db.query(TransactionSplit)
        .filter(TransactionSplit.transaction_id == txn_id, TransactionSplit.role == "expense")
        .first()
        .account
    )


def test_dry_run_plans_without_writing(db_session):
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    txn = _add_txn(db_session, "顺丰国际")
    db_session.commit()

    result = RuleService.rerun_rules(db_session, dry_run=True)
    assert result["updated"] == 1
    assert result["changes"] == [{
        "transaction_id": txn.id, "merchant": "顺丰国际", "date": "2026-01-01",
        "old_account": "Expenses:Uncategorized", "new_account": "Expenses:Delivery", "rule": "顺丰",
    }]
    # 未落库
    db_session.expire_all()
    assert _expense_account(db_session, txn.id) == "Expenses:Uncategorized"


def test_apply_updates_split_and_keeps_status(db_session):
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    txn = _add_txn(db_session, "顺丰国际")
    db_session.commit()

    result = RuleService.rerun_rules(db_session, dry_run=False)
    db_session.commit()
    assert result["updated"] == 1
    db_session.expire_all()
    assert _expense_account(db_session, txn.id) == "Expenses:Delivery"
    assert txn.status == "REVIEW_REQUIRED"  # 状态不变
    assert db_session.query(AuditLog).filter(AuditLog.action == "RERUN").count() == 1


def test_confirmed_and_income_excluded(db_session):
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    confirmed = _add_txn(db_session, "顺丰国际", status="CONFIRMED")
    income = _add_txn(db_session, "顺丰国际", direction="收入", cat="Income:BeanWEB")
    db_session.commit()

    result = RuleService.rerun_rules(db_session, dry_run=False)
    assert result["total"] == 1  # CONFIRMED 不进 scope
    assert result["updated"] == 0
    assert result["skipped_income"] == 1
    assert result["changes"] == []
    db_session.expire_all()
    assert _expense_account(db_session, confirmed.id) == "Expenses:Uncategorized"
    assert _expense_account(db_session, income.id) == "Income:BeanWEB"


def test_same_account_counts_unchanged(db_session):
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    txn = _add_txn(db_session, "顺丰国际", cat="Expenses:Delivery")
    db_session.commit()

    result = RuleService.rerun_rules(db_session, dry_run=True)
    assert result["updated"] == 0
    assert result["unchanged_same_account"] == 1


def test_transaction_ids_filter(db_session):
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    a = _add_txn(db_session, "顺丰国际")
    b = _add_txn(db_session, "顺丰国际二号店")
    db_session.commit()

    result = RuleService.rerun_rules(db_session, dry_run=True, transaction_ids=[a.id])
    assert [c["transaction_id"] for c in result["changes"]] == [a.id]


def test_route_apply_commits_and_defaults_dry_run(db_session):
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    txn = _add_txn(db_session, "顺丰国际")
    db_session.commit()

    # 默认 dry_run=True：不落库
    plan = apply_rules({"transaction_ids": [txn.id]}, db=db_session)
    assert plan["dry_run"] is True and plan["updated"] == 1
    db_session.expire_all()
    assert _expense_account(db_session, txn.id) == "Expenses:Uncategorized"

    # dry_run=False：路由内 commit
    done = apply_rules({"transaction_ids": [txn.id], "dry_run": False}, db=db_session)
    assert done["updated"] == 1
    db_session.expire_all()
    assert _expense_account(db_session, txn.id) == "Expenses:Delivery"


def test_route_rejects_bad_ids_type(db_session):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        apply_rules({"transaction_ids": "not-a-list"}, db=db_session)
    assert exc.value.status_code == 400


def test_legacy_split_without_role_fallback(db_session):
    """历史数据无 role：按 Assets: 前缀推断支付腿，其余视为分类腿（与 render_preview 同口径）"""
    _add_rule(db_session, "顺丰", "顺丰国际", "Expenses:Delivery")
    db_session.add(Transaction(
        date="2026-01-01", amount="10.00", merchant="顺丰国际", description="",
        counterparty="", direction="支出", status="REVIEW_REQUIRED",
    ))
    db_session.flush()
    txn = db_session.query(Transaction).order_by(Transaction.id.desc()).first()
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Expenses:Uncategorized", amount="10.00"))
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Assets:BeanWEB", amount="-10.00"))
    db_session.commit()

    result = RuleService.rerun_rules(db_session, dry_run=False)
    db_session.commit()
    assert result["updated"] == 1
    db_session.expire_all()
    splits = db_session.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()
    cat = next(s for s in splits if not s.account.startswith("Assets:"))
    assert cat.account == "Expenses:Delivery"
