from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.models import Transaction, AuditLog
from app.services.review import ReviewService
from typing import List, Optional

router = APIRouter(prefix="/api/transactions")

@router.get("/")
def get_transactions(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Transaction).options(joinedload(Transaction.splits))
    if status:
        query = query.filter(Transaction.status == status)
    return query.all()

@router.get("/{txn_id}")
def get_transaction(txn_id: int, db: Session = Depends(get_db)):
    txn = (
        db.query(Transaction)
        .options(joinedload(Transaction.splits))
        .filter(Transaction.id == txn_id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn

@router.patch("/{txn_id}")
def update_transaction(txn_id: int, update_data: dict, db: Session = Depends(get_db)):
    try:
        ReviewService.update_transaction(db, txn_id, update_data)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{txn_id}/confirm")
def confirm_transaction(txn_id: int, db: Session = Depends(get_db)):
    ReviewService.change_status(db, txn_id, "CONFIRMED", "Confirmed by user")
    return {"status": "success"}

@router.post("/{txn_id}/ignore")
def ignore_transaction(txn_id: int, db: Session = Depends(get_db)):
    ReviewService.change_status(db, txn_id, "IGNORED", "Ignored by user")
    return {"status": "success"}

@router.get("/{txn_id}/audit-logs")
def get_audit_logs(txn_id: int, db: Session = Depends(get_db)):
    return db.query(AuditLog).filter(AuditLog.entity_id == txn_id, AuditLog.entity_type == "transaction").all()
