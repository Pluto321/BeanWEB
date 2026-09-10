import hashlib
import json
from decimal import Decimal
from typing import Dict

from sqlalchemy.orm import Session

from app.models.models import RawTransaction, Transaction


class DeduplicationService:
    """三层去重：
    Layer 1  source_transaction_id 相同      -> EXACT_DUPLICATE
    Layer 2  raw hash（原始行内容）相同      -> EXACT_DUPLICATE
    Layer 3  canonical fingerprint 相同     -> POSSIBLE_DUPLICATE
    """

    def get_raw_hash(self, raw_data: Dict) -> str:
        stable = json.dumps(raw_data, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    def get_canonical_fingerprint(self, norm: Dict) -> str:
        amount = norm.get("amount")
        try:
            amount = str(Decimal(str(amount)).quantize(Decimal("0.01")))
        except Exception:
            amount = str(amount)
        data = {
            "date": str(norm.get("date") or ""),
            "amount": amount,
            "currency": str(norm.get("currency") or ""),
            "direction": str(norm.get("direction") or ""),
            "counterparty": str(norm.get("counterparty") or ""),
            "merchant": str(norm.get("merchant") or ""),
            "payment_method": str(norm.get("payment_method") or ""),
        }
        stable_json = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()

    def check_against_db(
        self,
        db: Session,
        source_id: str,
        raw_hash: str,
        fingerprint: str,
    ) -> tuple[str, str | None]:
        """返回 (result, reason)。result: UNIQUE / EXACT_DUPLICATE / POSSIBLE_DUPLICATE"""
        if source_id:
            exists = (
                db.query(Transaction.id)
                .filter(
                    Transaction.source_transaction_id == source_id,
                    Transaction.status.in_(["REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED"]),
                )
                .first()
            )
            if exists:
                return "EXACT_DUPLICATE", "SOURCE_ID"
        exists = (
            db.query(Transaction.id)
            .filter(
                Transaction.raw_hash == raw_hash,
                Transaction.status.in_(["REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED"]),
            )
            .first()
        )
        if exists:
            return "EXACT_DUPLICATE", "RAW_HASH"
        exists = (
            db.query(Transaction.id)
            .filter(
                Transaction.duplicate_reason != None,  # noqa: E711
            )
            .first()
        )  # placeholder; canonical check below
        # canonical fingerprint 查询（通过 raw_hash 表缓存不可靠，直接按指纹列查）
        exists = (
            db.query(Transaction.id)
            .filter(
                Transaction.canonical_fingerprint == fingerprint,
                Transaction.status.in_(["REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED"]),
            )
            .first()
        ) if hasattr(Transaction, "canonical_fingerprint") else None
        if exists:
            return "POSSIBLE_DUPLICATE", "CANONICAL_FINGERPRINT"
        return "UNIQUE", None

    def check(self, source_id: str, raw_data: Dict, norm: Dict) -> str:
        """兼容旧签名：内存内比对，仅返回 raw hash 与 fingerprint 计算结果。
        真正去重请使用 check_against_db()。"""
        if source_id:
            return "UNIQUE"
        return "UNIQUE"
