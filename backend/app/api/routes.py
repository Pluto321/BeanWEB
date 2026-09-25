from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.models import Transaction, TransactionSplit, AuditLog, ExportRecord
from app.services.review import ReviewService, AuditService
from typing import List, Optional

router = APIRouter(prefix="/api/transactions")


def _get_txn(db: Session, txn_id: int) -> Transaction:
    txn = (
        db.query(Transaction)
        .options(joinedload(Transaction.splits))
        .filter(Transaction.id == txn_id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.get("/")
def get_transactions(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Transaction).options(joinedload(Transaction.splits))
    if status:
        query = query.filter(Transaction.status == status)
    return query.all()


@router.get("/{txn_id}")
def get_transaction(txn_id: int, db: Session = Depends(get_db)):
    return _get_txn(db, txn_id)


@router.patch("/{txn_id}")
def update_transaction(txn_id: int, update_data: dict, db: Session = Depends(get_db)):
    try:
        ReviewService.update_transaction(db, txn_id, update_data)
        db.commit()
        return {"status": "success"}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{txn_id}/preview")
def preview_bean(txn_id: int, db: Session = Depends(get_db)):
    """导出前实时预览 Beancount 分录（与 Export 同一渲染逻辑）"""
    from app.services.export_service import ExportService
    txn = _get_txn(db, txn_id)
    try:
        return {"preview": ExportService._render(db, txn)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{txn_id}/splits")
def replace_splits(txn_id: int, data: dict, db: Session = Depends(get_db)):
    """整体替换交易的分片（支持多支付/多分类账户），并做金额平衡校验。

    请求体：
    {
      "splits": [{"account": "Expenses:Food", "amount": "70.00"}, ...],
      "payment_splits": [{"account": "Assets:Bank:CCB", "amount": "60.00"}, ...]
    }
    payment_splits 若提供，其合计必须等于交易金额；否则报错。
    """
    from decimal import Decimal, InvalidOperation
    from app.core.config import settings

    txn = _get_txn(db, txn_id)
    splits_data = data.get("splits") or []
    payment_data = data.get("payment_splits") or []

    def _parse_amount(v, label):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            raise HTTPException(status_code=400, detail=f"{label} 金额不合法: {v}")

    txn_amount = _parse_amount(txn.amount, "交易")

    payment_total = sum(_parse_amount(p["amount"], "支付账户") for p in payment_data)
    if payment_data and payment_total != txn_amount:
        raise HTTPException(status_code=400, detail="支付方式账户分配金额必须等于交易金额")

    expense_total = sum(_parse_amount(s["amount"], "分片") for s in splits_data)
    if splits_data and expense_total != txn_amount:
        raise HTTPException(status_code=400, detail="交易对方账户分配金额必须等于交易金额")

    try:
        old_splits = [{"account": s.account, "amount": s.amount} for s in txn.splits]

        # 确定最终 split 集合：显式 payment_splits 优先；否则用 splits；否则默认
        final_splits = []
        if payment_data:
            for p in payment_data:
                final_splits.append({"account": p["account"], "amount": str(_parse_amount(p["amount"], "支付")), "role": "payment"})
        for s in splits_data:
            final_splits.append({"account": s["account"], "amount": str(_parse_amount(s["amount"], "分片")), "role": "expense"})
        if not final_splits:
            final_splits.append({"account": settings.DEFAULT_EXPENSES_ACCOUNT, "amount": str(txn_amount), "role": "expense"})

        AuditLogService = None
        from app.services.review import AuditService
        AuditService.log_change(
            db, "transaction", txn.id, "SPLITS_REPLACE",
            {"splits": old_splits}, {"splits": final_splits},
            "User edited account allocation",
        )

        if txn.status == "CONFIRMED" and final_splits != old_splits:
            AuditService.log_change(
                db, "transaction", txn.id, "STATUS_CHANGE",
                {"status": "CONFIRMED"}, {"status": "REVIEW_REQUIRED"},
                "Confirmed transaction edited, reconfirmation required",
            )
            txn.status = "REVIEW_REQUIRED"

        db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).delete()
        for s in final_splits:
            db.add(TransactionSplit(
                transaction_id=txn.id,
                account=s["account"],
                amount=s["amount"],
                role=s.get("role", "expense"),
            ))
        db.commit()
        return {"status": "success", "splits": final_splits}
    except HTTPException:
        raise
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{txn_id}/splits/{split_id}")
def update_split(txn_id: int, split_id: int, data: dict, db: Session = Depends(get_db)):
    """修改分片的账户/金额"""
    _get_txn(db, txn_id)
    split = db.query(TransactionSplit).filter(
        TransactionSplit.id == split_id,
        TransactionSplit.transaction_id == txn_id,
    ).first()
    if not split:
        raise HTTPException(status_code=404, detail="Split not found")
    try:
        ReviewService.update_split(db, split_id, account=data.get("account"), amount=data.get("amount"))
        db.commit()
        return {"status": "success"}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch-skip")
def batch_skip(data: dict, db: Session = Depends(get_db)):
    """批量跳过：transaction_ids 中的交易标记为 IGNORED"""
    ids = data.get("transaction_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="transaction_ids 不能为空")
    skipped = []
    for tid in ids:
        try:
            txn = ReviewService.set_status(db, tid, "IGNORED", "User skipped", commit=False)
            skipped.append({"transaction_id": tid, "ok": True})
        except ValueError as e:
            db.rollback()
            skipped.append({"transaction_id": tid, "ok": False, "error": str(e)})
    db.commit()
    return {"skipped": skipped}


@router.post("/{txn_id}/confirm")
def confirm_transaction(txn_id: int, db: Session = Depends(get_db)):
    ReviewService.set_status(db, txn_id, "CONFIRMED", "Confirmed by user")
    return {"status": "success"}


@router.post("/{txn_id}/ignore")
def ignore_transaction(txn_id: int, db: Session = Depends(get_db)):
    ReviewService.set_status(db, txn_id, "IGNORED", "Ignored by user")
    return {"status": "success"}


@router.delete("/{txn_id}")
def delete_transaction(txn_id: int, db: Session = Depends(get_db)):
    """永久删除交易（含分片）。已导出的交易不允许删除。
    RawTransaction 保留（不可变原则），仅删除业务层 Transaction。"""
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    has_export = db.query(ExportRecord).filter(
        ExportRecord.transaction_id == txn_id, ExportRecord.status == "EXPORTED"
    ).first()
    if has_export:
        raise HTTPException(status_code=409, detail="已导出的交易不能删除")

    old = {"merchant": txn.merchant, "amount": txn.amount, "date": txn.date, "status": txn.status}
    db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn_id).delete()
    AuditService.log_change(db, "transaction", txn_id, "DELETE", old, None, "Transaction deleted by user")
    db.delete(txn)
    db.commit()
    return {"status": "success"}


@router.get("/{txn_id}/audit-logs")
def get_audit_logs(txn_id: int, db: Session = Depends(get_db)):
    return db.query(AuditLog).filter(AuditLog.entity_id == txn_id, AuditLog.entity_type == "transaction").all()
