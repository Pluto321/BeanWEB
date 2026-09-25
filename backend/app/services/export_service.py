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
    def _ensure_include_chain(ledger_mgr: LedgerManager, date_str: str):
        """确保年度文件与 main.bean include 链存在（导出与重导出共用）"""
        year_include = f"generated/{date_str[:4]}.bean"
        year_file = os.path.join(ledger_mgr.generated_dir, f"{date_str[:4]}.bean")
        if not os.path.exists(year_file):
            ledger_mgr._atomic_write(year_file, f'include "{date_str[:4]}/{date_str[5:7]}.bean"\n')
        ledger_mgr.update_include(
            os.path.join(ledger_mgr.ledger_dir, "main.bean"), year_include
        )

    @staticmethod
    def rewrite_month_fragment(
        db: Session,
        ledger_mgr: LedgerManager,
        year: str,
        month: str,
        include_record_id: int | None = None,
    ) -> str:
        """从数据库整体重生成某月的 .bean fragment。

        原则：.bean 是生成制品，SQLite 是 Source of Truth。
        渲染该月所有"活跃导出记录"（status=EXPORTED）对应的交易，整体原子写入。
        include_record_id 用于重导出：新记录尚处于 EXPORTING 中间态时，
        通过 id 显式纳入，避免"先置 EXPORTED 再回滚"的双活跃记录问题。

        重导出因此天然幂等：不会产生重复分录，同月其他交易的分录
        也会按最新 DB 状态归一化。返回 fragment 路径。
        """
        from sqlalchemy import or_
        prefix = f"{year}-{month}-"
        q = (
            db.query(Transaction)
            .join(ExportRecord, ExportRecord.transaction_id == Transaction.id)
            .filter(Transaction.date.like(f"{prefix}%"))
            .order_by(Transaction.date, Transaction.id)
        )
        if include_record_id is not None:
            q = q.filter(or_(ExportRecord.status == "EXPORTED", ExportRecord.id == include_record_id))
        else:
            q = q.filter(ExportRecord.status == "EXPORTED")
        rows = q.all()
        parts = [ExportService._render(db, txn) for txn in rows]
        year_dir = os.path.join(ledger_mgr.generated_dir, year)
        os.makedirs(year_dir, exist_ok=True)
        fragment_path = os.path.join(year_dir, f"{month}.bean")
        content = ("\n".join(parts) + "\n") if parts else ""
        ledger_mgr._atomic_write(fragment_path, content)
        return fragment_path

    @staticmethod
    def _fragment_year_month(path: str) -> tuple[str, str] | None:
        """从 fragment 路径解析 (year, month)：.../generated/YYYY/MM.bean"""
        if not path:
            return None
        norm = path.replace("\\", "/")
        if "/generated/" not in norm:
            return None
        rel = norm.split("/generated/")[-1]  # YYYY/MM.bean
        parts = rel.split("/")
        if len(parts) != 2 or not parts[1].endswith(".bean"):
            return None
        year, month = parts[0], parts[1][: -len(".bean")]
        if len(year) != 4 or len(month) != 2:
            return None
        return year, month

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
            ExportService._ensure_include_chain(ledger_mgr, txn.date)

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
    def reexport_transaction(db: Session, txn_id: int) -> ExportRecord:
        """重导出：交易导出后被编辑（CONFIRMED → REVIEW_REQUIRED → 重新 CONFIRMED），
        用新内容替换 .bean 中的旧分录。

        机制：
        1. 旧活跃记录标记 SUPERSEDED（保留历史，不删除）
        2. 创建新的 EXPORTED 记录
        3. 按当前数据库状态整体重生成受影响的月度 fragment（无重复分录）
        4. 若编辑时改了日期导致跨月，旧月 fragment 同步重生成
        """
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
        if not existing:
            raise ValueError("该交易尚未导出过，请使用普通导出")

        old_fragment = existing.file_path

        # 1. 旧记录 → SUPERSEDED
        existing.status = "SUPERSEDED"
        db.add(AuditLog(
            entity_type="export",
            entity_id=existing.id,
            action="SUPERSEDED",
            old_value={"status": "EXPORTED"},
            new_value={"status": "SUPERSEDED"},
            timestamp=datetime.now(),
            user_note=f"Superseded by re-export of transaction {txn_id}",
        ))
        db.flush()

        # 2. 新记录
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

            # 3. 重生成交易当前所属月份的 fragment（旧记录已 SUPERSEDED 被排除，
            #    新记录通过 include_record_id 显式纳入，分录恰好出现一次）
            new_fragment = ExportService.rewrite_month_fragment(
                db, ledger_mgr, txn.date[:4], txn.date[5:7], include_record_id=record.id
            )
            ExportService._ensure_include_chain(ledger_mgr, txn.date)

            # 4. 跨月：编辑改了日期时，旧月 fragment 同步重生成（移除旧分录）
            old_ym = ExportService._fragment_year_month(old_fragment)
            if old_ym and (old_ym[0], old_ym[1]) != (txn.date[:4], txn.date[5:7]):
                ExportService.rewrite_month_fragment(db, ledger_mgr, old_ym[0], old_ym[1])

            record.file_path = new_fragment
            record.file_sha256 = ExportService._file_sha256(new_fragment) or ""
            record.status = "EXPORTED"
            record.completed_at = datetime.now()

            db.add(AuditLog(
                entity_type="export",
                entity_id=record.id,
                action="REEXPORT",
                old_value={"superseded_record": existing.id},
                new_value={"file": new_fragment, "transaction_id": txn_id},
                timestamp=datetime.now(),
                user_note="Re-export edited transaction",
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
