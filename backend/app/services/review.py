from sqlalchemy.orm import Session
from datetime import datetime
from app.models.models import Transaction, TransactionSplit, AuditLog
from typing import Dict, Any, Optional
from decimal import Decimal, InvalidOperation


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
    EDITABLE_FIELDS = {
        "date", "time", "amount", "currency", "merchant", "description",
        "payment_method", "counterparty", "direction",
    }

    @staticmethod
    def update_transaction(db: Session, txn_id: int, update_data: Dict[str, Any]):
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise ValueError("Transaction not found")

        if txn.status == "EXPORTED":
            raise ValueError("已导出的交易不能修改")

        old_values = {}
        new_values = {}

        # 记录变化字段
        for field, value in update_data.items():
            if field not in ReviewService.EDITABLE_FIELDS:
                continue
            old_val = getattr(txn, field)
            if old_val != value:
                old_values[field] = old_val
                new_values[field] = value
                setattr(txn, field, value)

        if old_values:
            AuditService.log_change(db, "transaction", txn_id, "UPDATE", old_values, new_values, "User manual update")
            # CONFIRMED 交易被编辑后必须重新确认
            if txn.status == "CONFIRMED":
                AuditService.log_change(
                    db, "transaction", txn_id, "STATUS_CHANGE",
                    {"status": "CONFIRMED"}, {"status": "REVIEW_REQUIRED"},
                    "Confirmed transaction edited, reconfirmation required",
                )
                txn.status = "REVIEW_REQUIRED"


    @staticmethod
    def update_split(
        db: Session,
        split_id: int,
        account: Optional[str] = None,
        amount: Optional[str] = None,
    ):
        """修改单个分片的账户或金额，产生审计日志"""
        split = db.query(TransactionSplit).filter(TransactionSplit.id == split_id).first()
        if not split:
            raise ValueError("Split not found")

        old = {"account": split.account, "amount": split.amount}
        changed = False
        if account is not None and account.strip():
            new_account = account.strip()
            if new_account != split.account:
                split.account = new_account
                changed = True
        if amount is not None:
            try:
                Decimal(amount)
            except InvalidOperation:
                raise ValueError(f"金额不合法: {amount}")
            if amount != split.amount:
                split.amount = amount
                changed = True
        if changed:
            AuditService.log_change(
                db, "split", split_id, "UPDATE",
                old, {"account": split.account, "amount": split.amount},
                "User manual update split",
            )
        return split


    @staticmethod
    def set_status(db: Session, txn_id: int, new_status: str, note: str = "", commit: bool = True):
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise ValueError("Transaction not found")

        old_status = txn.status
        if old_status != new_status:
            txn.status = new_status
            AuditService.log_change(db, "transaction", txn_id, "STATUS_CHANGE", {"status": old_status}, {"status": new_status}, note)
        if commit:
            db.commit()
        return txn

    @staticmethod
    def change_status(db: Session, txn_id: int, new_status: str, note: str = ""):
        """兼容旧测试签名的状态变更（内部自动 commit）"""
        return ReviewService.set_status(db, txn_id, new_status, note, commit=True)
