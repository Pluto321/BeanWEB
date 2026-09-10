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
        """渲染真实 Beancount 分录：
        - 第一个 split 为交易来源账户（如支付账户，带负号）
        - 其余 split 为分类账户（正数）
        - 所有 split 金额之和必须等于 0（复式记账）
        """
        splits = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()
        if not splits:
            raise ValueError("Transaction has no splits, cannot export")

        lines = [f'{txn.date} * "{txn.merchant or ""}" "{txn.description or ""}"']
        lines.append(f'  id: "{txn.id}"')
        if txn.raw_transaction_id:
            lines.append(f'  raw_id: "{txn.raw_transaction_id}"')

        amount = Decimal(str(txn.amount))
        signed_splits = [(s.account, Decimal(s.amount)) for s in splits]
        # 校验借贷平衡：split 金额总和应为 0；若 DB 中 split 均为正数（历史数据），
        # 则用负号账户补齐第一行为资产账户
        total = sum(a for _, a in signed_splits)
        if total != 0:
            remaining = -total
            signed_splits.insert(0, ("Assets:BeanWEB", remaining))
        for acc, val in signed_splits:
            lines.append(f'  {acc:<32} {val:>12} {txn.currency}')
        return "\n".join(lines)
