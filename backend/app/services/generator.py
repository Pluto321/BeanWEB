from decimal import Decimal
from typing import List
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.models import Transaction, TransactionSplit, AuditLog
import os

class BeancountGenerator:
    @staticmethod
    def generate_transaction(txn: Transaction) -> str:
        lines = []
        # 日期 * "Payee" "Description"
        payee = txn.merchant or ""
        description = txn.description or ""
        lines.append(f'{txn.date} * "{payee}" "{description}"')
        
        # Metadata
        lines.append(f'  id: "{txn.id}"')
        lines.append(f'  raw_id: "{txn.raw_transaction_id}"')
        
        # Splits
        for split in txn.splits:
            amount = Decimal(split.amount).quantize(Decimal("0.01"))
            lines.append(f'  {split.account:<30} {amount:>12} {txn.currency}')
        
        return "\n".join(lines)

class ExportService:
    @staticmethod
    def export_confirmed(db: Session, export_dir: str):
        txns = db.query(Transaction).filter(Transaction.status == "CONFIRMED").all()
        if not txns:
            return None
        
        os.makedirs(export_dir, exist_ok=True)
        filename = f"export_{datetime.now().strftime('%Y%m%d%H%M%S')}.bean"
        filepath = os.path.join(export_dir, filename)
        
        content = []
        txn_ids = []
        
        for txn in txns:
            content.append(BeancountGenerator.generate_transaction(txn))
            txn_ids.append(txn.id)
            txn.status = "EXPORTED"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n\n".join(content))
            
        # 记录审计
        log = AuditLog(
            entity_type="export",
            entity_id=0,
            action="EXPORT",
            new_value={"txn_ids": txn_ids, "file": filename},
            timestamp=datetime.now(),
            user_note="Batch export confirmed transactions"
        )
        db.add(log)
        db.commit()
        return filepath
