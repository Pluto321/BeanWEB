from sqlalchemy.orm import Session
from app.models.models import Transaction, TransactionSplit, AuditLog
from decimal import Decimal
from typing import List, Dict, Any
from datetime import datetime

class SplitService:
    @staticmethod
    def validate_balance(splits: List[Dict[str, Any]]):
        total = sum(Decimal(str(s['amount'])) for s in splits)
        return total == Decimal("0.00")

    @staticmethod
    def update_transaction_with_splits(db: Session, txn_id: int, splits_data: List[Dict[str, Any]], note: str = ""):
        if not SplitService.validate_balance(splits_data):
            raise ValueError("Transaction splits must balance to zero")
            
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise ValueError("Transaction not found")
        
        # 记录审计日志：删除旧 splits，添加新 splits
        old_splits = [
            {"account": s.account, "amount": s.amount} 
            for s in db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn_id).all()
        ]
        
        # 删除旧数据
        db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn_id).delete()
        
        # 添加新数据
        new_splits = []
        for s in splits_data:
            split = TransactionSplit(
                transaction_id=txn_id,
                account=s['account'],
                amount=str(Decimal(str(s['amount']))) # 确保存入标准化字符串
            )
            new_splits.append(split)
        
        db.add_all(new_splits)
        
        # 记录审计日志
        log = AuditLog(
            entity_type="transaction",
            entity_id=txn_id,
            action="UPDATE_SPLITS",
            old_value={"splits": old_splits},
            new_value={"splits": splits_data},
            timestamp=datetime.now(),
            user_note=note
        )
        db.add(log)
        db.commit()
