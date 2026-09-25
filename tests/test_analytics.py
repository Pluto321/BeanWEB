"""统计分析 API 验证：月度汇总 Decimal 正确性、分类占比、scope 口径。"""
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.models import Base, Transaction, TransactionSplit
from app.api.analytics import monthly, trend


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _mk(db, tid, date, amount, direction, merchant, status="CONFIRMED", cat="Expenses:Food", pay="Assets:Alipay"):
    t = Transaction(
        id=tid, raw_transaction_id=None, date=date, amount=amount,
        currency="CNY", merchant=merchant, description="", direction=direction,
        status=status,
    )
    db.add(t)
    db.flush()
    db.add(TransactionSplit(transaction_id=t.id, account=cat, amount=amount, role="expense"))
    db.add(TransactionSplit(
        transaction_id=t.id, account=pay,
        amount=str(-Decimal(amount)) if direction == "支出" else amount,
        role="payment",
    ))
    db.commit()
    return t


def test_monthly_sums_and_categories(db_session):
    _mk(db_session, 1, "2026-09-01", "100.00", "支出", "美团")
    _mk(db_session, 2, "2026-09-05", "50.50", "支出", "京东", cat="Expenses:Shopping")
    _mk(db_session, 3, "2026-09-10", "3000.00", "收入", "某公司", cat="Income:Salary", pay="Assets:Bank")
    # 其他月份与 IGNORED 不应计入
    _mk(db_session, 4, "2026-08-15", "99.00", "支出", "八月")
    _mk(db_session, 5, "2026-09-20", "77.00", "支出", "被忽略", status="IGNORED")

    r = monthly(month="2026-09", scope="confirmed", db=db_session)
    assert r["transaction_count"] == 3
    assert r["expense"] == "150.50"
    assert r["income"] == "3000.00"
    assert r["net"] == "2849.50"
    # 分类只含支出侧：Food + Shopping，不含 Income:Salary
    accounts = [c["account"] for c in r["categories"]]
    assert "Expenses:Food" in accounts and "Expenses:Shopping" in accounts
    assert not any(a.startswith("Income") for a in accounts)
    food = next(c for c in r["categories"] if c["account"] == "Expenses:Food")
    assert food["amount"] == "100.00"
    assert Decimal(food["ratio"]) == (Decimal("100.00") / Decimal("150.50")).quantize(Decimal("0.0001"))
    # 商户 Top 按金额降序
    assert [m["merchant"] for m in r["merchants"]] == ["美团", "京东"]


def test_monthly_scope_active_includes_review(db_session):
    _mk(db_session, 1, "2026-09-01", "100.00", "支出", "已确认")
    _mk(db_session, 2, "2026-09-02", "200.00", "支出", "待审核", status="REVIEW_REQUIRED")

    confirmed = monthly(month="2026-09", scope="confirmed", db=db_session)
    assert confirmed["transaction_count"] == 1
    assert confirmed["expense"] == "100.00"

    active = monthly(month="2026-09", scope="active", db=db_session)
    assert active["transaction_count"] == 2
    assert active["expense"] == "300.00"


def test_monthly_empty_and_default_month(db_session):
    r = monthly(month="2026-01", scope="confirmed", db=db_session)
    assert r["transaction_count"] == 0
    assert r["income"] == "0.00" and r["expense"] == "0.00"
    assert r["categories"] == [] and r["merchants"] == []
    # 缺省 month 不报错
    r2 = monthly(db=db_session)
    assert "month" in r2


def test_trend(db_session):
    _mk(db_session, 1, "2026-09-01", "100.00", "支出", "a")
    _mk(db_session, 2, "2026-09-02", "500.00", "收入", "b")
    r = trend(months=6, scope="confirmed", db=db_session)
    assert len(r["months"]) == 6
    sept = next(m for m in r["months"] if m["month"] == "2026-09")
    assert sept["expense"] == "100.00"
    assert sept["income"] == "500.00"
    assert sept["count"] == 2
    assert sept["net"] == "400.00"
