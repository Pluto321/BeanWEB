"""统计分析 API：月度收支汇总、支出分类占比、商户 Top、收支趋势。
只读聚合，金额全程 Decimal（返回字符串），不依赖 Fava。"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Transaction, TransactionSplit

router = APIRouter(prefix="/api/analytics")

# confirmed = 已确认（已审核的业务事实）；active = 全部未忽略（含待审核/疑似重复）
SCOPES: dict[str, list[str]] = {
    "confirmed": ["CONFIRMED"],
    "active": ["REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED"],
}


def _resolve_scope(scope: str) -> list[str]:
    return SCOPES.get(scope, SCOPES["confirmed"])


def _is_expense_side(t: Transaction) -> bool:
    return (t.direction or "支出") != "收入"


def _month_txns(db: Session, month: str, statuses: list[str]) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.status.in_(statuses), Transaction.date.like(f"{month}-%"))
        .order_by(Transaction.date, Transaction.id)
        .all()
    )


def _split_map(db: Session, txn_ids: list[int]) -> dict[int, list[TransactionSplit]]:
    if not txn_ids:
        return {}
    splits = db.query(TransactionSplit).filter(TransactionSplit.transaction_id.in_(txn_ids)).all()
    result: dict[int, list[TransactionSplit]] = {}
    for s in splits:
        result.setdefault(s.transaction_id, []).append(s)
    return result


def _is_payment_split(s: TransactionSplit) -> bool:
    if getattr(s, "role", None):
        return s.role == "payment"
    return bool(s.account) and s.account.startswith("Assets:")


@router.get("/monthly")
def monthly(month: str | None = None, scope: str = "confirmed", db: Session = Depends(get_db)):
    """月度收支汇总 + 支出分类占比 + 商户 Top。

    month 格式 YYYY-MM，缺省为当前月。
    scope: confirmed（仅已确认，默认）/ active（全部未忽略，含待审核）。
    """
    if not month:
        month = datetime.now().strftime("%Y-%m")
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="month 格式应为 YYYY-MM")

    statuses = _resolve_scope(scope)
    txns = _month_txns(db, month, statuses)
    smap = _split_map(db, [t.id for t in txns])

    income = Decimal("0")
    expense = Decimal("0")
    cat_map: dict[str, list] = {}      # account -> [total, count]
    mer_map: dict[str, list] = {}     # merchant -> [total, count]
    pay_map: dict[str, list] = {}      # payment account -> [total, count]

    for t in txns:
        amt = Decimal(str(t.amount))
        if _is_expense_side(t):
            expense += amt
        else:
            income += amt
        for s in smap.get(t.id, []):
            if _is_payment_split(s):
                bucket = pay_map.setdefault(s.account, [Decimal("0"), 0])
                bucket[0] += Decimal(str(s.amount)); bucket[1] += 1
            elif _is_expense_side(t):
                # 分类只统计支出侧（收入侧是 Income: 来源账户，不混入支出占比）
                bucket = cat_map.setdefault(s.account, [Decimal("0"), 0])
                bucket[0] += Decimal(str(s.amount)); bucket[1] += 1
        if _is_expense_side(t):
            mb = mer_map.setdefault(t.merchant or "未指定商户", [Decimal("0"), 0])
            mb[0] += amt; mb[1] += 1

    def _sorted(m: dict, limit: int | None = None):
        items = sorted(m.items(), key=lambda kv: kv[1][0], reverse=True)
        if limit:
            items = items[:limit]
        return items

    categories = []
    for account, (total, count) in _sorted(cat_map):
        ratio = (total / expense) if expense > 0 else Decimal("0")
        categories.append({
            "account": account, "amount": str(total), "count": count,
            "ratio": str(ratio.quantize(Decimal("0.0001"))),
        })
    merchants = [
        {"merchant": m, "amount": str(total), "count": count}
        for m, (total, count) in _sorted(mer_map, 10)
    ]
    payments = [
        {"account": a, "amount": str(total), "count": count}
        for a, (total, count) in _sorted(pay_map)
    ]

    return {
        "month": month,
        "scope": scope if scope in SCOPES else "confirmed",
        "transaction_count": len(txns),
        "income": str(income.quantize(Decimal("0.01"))),
        "expense": str(expense.quantize(Decimal("0.01"))),
        "net": str((income - expense).quantize(Decimal("0.01"))),
        "categories": categories,
        "merchants": merchants,
        "payment_accounts": payments,
    }


@router.get("/trend")
def trend(months: int = 6, scope: str = "confirmed", db: Session = Depends(get_db)):
    """最近 N 个月（含当月）收支趋势。"""
    if months < 1 or months > 36:
        months = 6
    statuses = _resolve_scope(scope)
    now = datetime.now()
    month_keys: list[str] = []
    for i in range(months - 1, -1, -1):
        total = now.year * 12 + (now.month - 1) - i
        month_keys.append(f"{total // 12}-{total % 12 + 1:02d}")

    earliest = month_keys[0]
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.status.in_(statuses),
            Transaction.date >= f"{earliest}-01",
        )
        .order_by(Transaction.date, Transaction.id)
        .all()
    )
    agg: dict[str, dict[str, Decimal]] = {m: {"income": Decimal("0"), "expense": Decimal("0")} for m in month_keys}
    counts: dict[str, int] = {m: 0 for m in month_keys}
    for t in txns:
        key = (t.date or "")[:7]
        if key not in agg:
            continue
        counts[key] += 1
        amt = Decimal(str(t.amount))
        if _is_expense_side(t):
            agg[key]["expense"] += amt
        else:
            agg[key]["income"] += amt

    return {
        "scope": scope if scope in SCOPES else "confirmed",
        "months": [
            {
                "month": m,
                "income": str(agg[m]["income"].quantize(Decimal("0.01"))),
                "expense": str(agg[m]["expense"].quantize(Decimal("0.01"))),
                "net": str((agg[m]["income"] - agg[m]["expense"]).quantize(Decimal("0.01"))),
                "count": counts[m],
            }
            for m in month_keys
        ],
    }
