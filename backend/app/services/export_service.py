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
        if txn.status == "IGNORED":
            raise ValueError("被跳过的交易不会导出")
        if txn.status != "CONFIRMED":
            raise ValueError("Only CONFIRMED transactions can be exported")

        existing = (
            db.query(ExportRecord)
            .filter(ExportRecord.transaction_id == txn_id, ExportRecord.status == "EXPORTED")
            .first()
        )
        if existing:
            raise ValueError("Transaction already exported")

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

            db.add(AuditLog(
                entity_type="export",
                entity_id=record.id,
                action="EXPORT",
                old_value=None,
                new_value={"file": fragment_path, "transaction_id": txn_id},
                user_note="Export confirmed transaction",
            ))
        except Exception as e:
            record.status = "FAILED"
            record.error_message = str(e)
            raise
        return record

    @staticmethod
    def render_preview(txn: Transaction, splits: list[TransactionSplit]) -> str:
        """从已加载的 Transaction + splits 渲染 Beancount 分录（无 DB 依赖，前端预览与导出共用同一逻辑）。

        语义（与 PUT /{id}/splits 写入口径一致）：
        - payment 账户（Assets，用户选择或默认）金额为负数（支出时）或正数（收入时）
        - expense 账户（Expenses/Income 等分类账户）金额为正数（支出时）或负数（收入时）
        - 用户通过 PUT splits 显式选择的 Assets 账户直接作为支付账户输出；
          未选择时用 settings.DEFAULT_ASSETS_ACCOUNT 兜底
        """
        if not splits:
            raise ValueError("Transaction has no splits, cannot export")

        lines = [f'{txn.date} * "{txn.merchant or ""}" "{txn.description or ""}"']
        lines.append(f'  id: "{txn.id}"')
        if txn.raw_transaction_id:
            lines.append(f'  raw_id: "{txn.raw_transaction_id}"')

        total = sum(Decimal(s.amount) for s in splits)
        direction = getattr(txn, "direction", None) or "支出"

        # 优先按 role 字段区分（payment/expense）；历史数据无 role 时按 Assets: 前缀推断
        def _is_payment(s) -> bool:
            if getattr(s, "role", None):
                return s.role == "payment"
            return s.account.startswith("Assets:")

        payment_splits = [(s.account, Decimal(s.amount)) for s in splits if _is_payment(s)]
        category_splits = [(s.account, Decimal(s.amount)) for s in splits if not _is_payment(s)]

        if not payment_splits:
            payment_splits = [(settings.DEFAULT_ASSETS_ACCOUNT, total)]

        # 支付账户若已带符号（导入自动匹配生成的 payment split 支出为负、收入为正），
        # 则直接使用；仅当金额与交易金额同号（未带符号的正数历史数据）时才按方向取负
        def _sign_payment(val: Decimal) -> Decimal:
            if val < 0:
                return val  # 已带负号（支出）
            return val if direction == "收入" else -val

        if direction == "收入":
            signed = [(acc, -val) for acc, val in category_splits]
            signed += [(acc, _sign_payment(val)) for acc, val in payment_splits]
        else:
            signed = [(acc, val) for acc, val in category_splits]
            signed += [(acc, _sign_payment(val)) for acc, val in payment_splits]

        for acc, val in signed:
            lines.append(f'  {acc:<32} {val:>12} {txn.currency}')
        return "\n".join(lines)

    @staticmethod
    def _render(db: Session, txn: Transaction) -> str:
        splits = db.query(TransactionSplit).filter(TransactionSplit.transaction_id == txn.id).all()
        return ExportService.render_preview(txn, splits)
