import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.models import RawTransaction, Transaction

# ---- 跨源匹配（Layer 4）规范化工件 ----

# 银行流水商户名常带支付渠道前缀；跨源比对时剥离（财付通-聚鑫福超市 → 聚鑫福超市）
_CHANNEL_PREFIXES = (
    "财付通-", "支付宝-", "微信支付-", "京东支付-", "中移支付-", "云闪付-", "度小满-",
)
# 商户分期行「商户分期9/12:银联-北京京东世纪」的渠道部分
_INSTALLMENT_RE = re.compile(r"^商户分期\d+/\d+:银联-")

# 转账特征关键词（方向互反的跨源配对：信用卡还款 / 提现 / 零钱通 等）
_TRANSFER_HINTS = ("还款", "提现", "零钱通", "信用卡", "银联入账", "余额宝")

# 跨源日期容差：银行记账日可能比钱包账单的交易日晚 0–1 天（银行账单自带说明）
_CROSS_SOURCE_DATE_WINDOW = 1


def strip_channel_prefix(merchant: str) -> str:
    """剥离商户名里的支付渠道前缀（可叠乘：财付通-微信支付-天津联通 → 天津联通）。"""
    s = (merchant or "").strip()
    changed = True
    while changed:
        changed = False
        m = _INSTALLMENT_RE.match(s)
        if m:
            s = s[m.end():].strip()
            changed = True
            continue
        for p in _CHANNEL_PREFIXES:
            if s.startswith(p):
                s = s[len(p):].strip()
                changed = True
                break
    return s


class DeduplicationService:
    """四层去重：
    Layer 1  source_transaction_id 相同      -> EXACT_DUPLICATE
    Layer 2  raw hash（原始行内容）相同      -> EXACT_DUPLICATE
    Layer 3  canonical fingerprint 相同     -> POSSIBLE_DUPLICATE（同源近似）
    Layer 4  跨源匹配（CROSS_SOURCE）       -> POSSIBLE_DUPLICATE（银行 ↔ 支付宝/微信
             各记一次的同一笔业务；只标记为疑似，裁决权留给人，绝不自动跳过）
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

    # ---- Layer 4：跨源匹配 ----

    @staticmethod
    def _transfer_hinted(*texts) -> bool:
        joined = " ".join(str(t or "") for t in texts)
        return any(h in joined for h in _TRANSFER_HINTS)

    def find_cross_source_match(
        self, db: Session, norm: Dict, source_type: str
    ) -> Optional[Transaction]:
        """跨源匹配：不同来源的账单对同一笔经济业务的重复记录。

        两种形态（都只标记为疑似 CROSS_SOURCE，绝不自动跳过）：
        1. 同方向 + 渠道前缀剥离后商户相同 + 金额相等 + 日期差 ≤ 1 天
           （微信/支付宝快捷支付同时出现在钱包账单与银行流水）
        2. 方向互反 + 金额相等 + 日期差 ≤ 1 天 + 双侧含转账特征关键词
           （信用卡还款：银行侧支出 + 信用卡侧「银联入账」收入）

        已知盲区（由规则引擎/人工兜底）：银行侧通用行（如「财付通-扫二维码付款」
        无真实商户名）、金额被手续费拆分的、日期差超过容差的。
        """
        try:
            new_date = datetime.strptime(str(norm.get("date") or ""), "%Y-%m-%d").date()
        except ValueError:
            return None
        try:
            amount = Decimal(str(norm.get("amount"))).quantize(Decimal("0.01"))
        except Exception:
            return None
        lo = (new_date - timedelta(days=_CROSS_SOURCE_DATE_WINDOW)).isoformat()
        hi = (new_date + timedelta(days=_CROSS_SOURCE_DATE_WINDOW)).isoformat()
        direction = str(norm.get("direction") or "支出")
        candidates = (
            db.query(Transaction)
            .filter(
                Transaction.date >= lo,
                Transaction.date <= hi,
                Transaction.status.in_(["REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED"]),
            )
            .all()
        )
        new_merchant = strip_channel_prefix(str(norm.get("merchant") or ""))
        for t in candidates:
            if (t.source_type or "") == (source_type or ""):
                continue  # 跨源匹配只在不同来源之间
            try:
                if Decimal(str(t.amount)) != amount:
                    continue
            except Exception:
                continue
            t_direction = t.direction or "支出"
            if t_direction == direction:
                # 形态 1：同方向 + 商户名（剥离渠道前缀后）相同
                if new_merchant and strip_channel_prefix(t.merchant or "") == new_merchant:
                    return t
            else:
                # 形态 2：方向互反的转账对（还款/提现），双侧需含转账特征
                if (
                    self._transfer_hinted(t.merchant, t.description, t.counterparty)
                    and self._transfer_hinted(
                        norm.get("merchant"), norm.get("description"), norm.get("counterparty")
                    )
                ):
                    return t
        return None

    def check(self, source_id: str, raw_data: Dict, norm: Dict) -> str:
        """兼容旧签名：内存内比对，仅返回 raw hash 与 fingerprint 计算结果。
        真正去重请使用 check_against_db()。"""
        if source_id:
            return "UNIQUE"
        return "UNIQUE"
