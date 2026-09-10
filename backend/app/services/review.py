from sqlalchemy.orm import Session
from datetime import datetime
from app.models.models import Transaction, TransactionSplit, AuditLog
from typing import Dict, Any

class AuditService:
    @staticmethod
    def log_change(db: Session, entity_type: str, entity_id: int, action: str, old_value: Dict, new_value: Dict, note: str = ""):
        log = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            timestamp=datetime.now(),
            user_note=note
        )
        db.add(log)

class ReviewService:
    @staticmethod
    def update_transaction(db: Session, txn_id: int, update_data: Dict[str, Any]):
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise ValueError("Transaction not found")
            
        old_values = {}
        new_values = {}
        
        # 记录变化字段
        for field, value in update_data.items():
            if hasattr(txn, field):
                old_val = getattr(txn, field)
                if old_val != value:
                    old_values[field] = old_val
                    new_values[field] = value
                    setattr(txn, field, value)
        
        if old_values:
            AuditService.log_change(db, "transaction", txn_id, "UPDATE", old_values, new_values, "User manual update")
            # 移除这里的 db.commit()，由调用者决定事务边界，防止在 test 中 commit 导致的 rollback 失效



    @staticmethod
    def change_status(db: Session, txn_id: int, new_status: str, note: str = ""):
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise ValueError("Transaction not found")
        
        old_status = txn.status
        if old_status != new_status:
            txn.status = new_status
            AuditService.log_change(db, "transaction", txn_id, "STATUS_CHANGE", {"status": old_status}, {"status": new_status}, note)
        db.commit()
