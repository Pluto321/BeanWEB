import hashlib
import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import ExportRecord, Transaction, TransactionSplit, AuditLog
from app.services.generator import BeancountGenerator
from app.services.ledger import LedgerManager
from app.core.config import settings


class ExportService:
    @staticmethod
    def _file_sha256(path: str) -> str | None:
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    @staticmethod
    def export_transaction(db: Session, txn_id: int) -> ExportRecord:
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if not txn:
            raise ValueError("Transaction not found")
        if txn.status != "CONFIRMED":
            raise ValueError("Only CONFIRMED transactions can be exported")

        existing = (
            db.query(ExportRecord)
            .filter(ExportRecord.transaction_id == txn_id, ExportRecord.status == "EXPORTED")
            .first()
        )
        if existing:
            if existing.file_path and ExportService._file_sha256(existing.file_path) == existing.file_sha256:
                raise ValueError("Transaction already exported")
            raise ValueError("Export record conflict: previous export file missing or corrupted")

        record = ExportRecord(transaction_id=txn_id, status="PENDING", file_path="", file_sha256="")
        db.add(record)
        db.flush()

        try:
            record.status = "EXPORTING"
            content = ExportService._render(db, txn)

            try:
                from beancount.parser import parser
                parser.parse_string(content)
            except ImportError:
                pass

            ledger_mgr = LedgerManager(settings.LEDGER_DIR)
            fragment_path = ledger_mgr.write_fragment(txn.date, content)
            year_include = f"generated/{txn.date[:4]}.bean"
            year_file = os.path.join(ledger_mgr.generated_dir, f"{txn.date[:4]}.bean")
            if not os.path.exists(year_file):
                ledger_mgr._atomic_write(year_file, f'include "{txn.date[:4]}/{txn.date[5:7]}.bean"\n')
            ledger_mgr.update_include(
                os.path.join(ledger_mgr.ledger_dir, "main.bean"), year_include
            )

            record.file_path = fragment_path
            record.file_sha256 = ExportService._file_sha256(fragment_path) or ""
            record.status = "EXPORTED"
            record.completed_at = datetime.now()

            AuditLog(
                entity_type="export",
                entity_id=record.id,
                action="EXPORT",
                old_value=None,
                new_value={"file": fragment_path, "transaction_id": txn_id},
                user_note="Export confirmed transaction",
            )
        except Exception as e:
            record.status = "FAILED"
            record.error_message = str(e)
            raise
        return record

    @staticmethod
    def _render(db: Session, txn: Transaction) -> str:
        splits = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()
        lines = [f'{txn.date} * "{txn.merchant or ""}" "{txn.description or ""}"']
        lines.append(f'  id: "{txn.id}"')
        if txn.raw_transaction_id:
            lines.append(f'  raw_id: "{txn.raw_transaction_id}"')
        amount = Decimal(str(txn.amount)).quantize(Decimal("0.01"))
        balance = -amount
        lines.append(f'  {"Assets:BeanWEB":<32} {amount:>12} {txn.currency}')
        for s in splits[:-1] if splits else []:
            lines.append(f'  {s.account:<32} {Decimal(s.amount):>12} {txn.currency}')
            balance += Decimal(s.amount)
        lines.append(f'  {"Expenses:Uncategorized":<32} {balance:>12} {txn.currency}')
        return "\n".join(lines)
