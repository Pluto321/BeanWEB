from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.models import Transaction, TransactionSplit, AuditLog
from app.services.review import ReviewService
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


@router.get("/{txn_id}/audit-logs")
def get_audit_logs(txn_id: int, db: Session = Depends(get_db)):
    return db.query(AuditLog).filter(AuditLog.entity_id == txn_id, AuditLog.entity_type == "transaction").all()
