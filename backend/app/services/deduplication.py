import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.models import RawTransaction, Transaction

# ---- 跨源匹配（Layer 4）规范化工件 ----

# 银行流水商户名常带支付渠道前缀；跨源比对时剥离（财付通-测试超市 → 测试超市）
_CHANNEL_PREFIXES = (
    "财付通-", "支付宝-", "微信支付-", "京东支付-", "中移支付-", "云闪付-", "度小满-",
)
# 商户分期行「商户分期9/12:银联-北京京东世纪」的渠道部分
_INSTALLMENT_RE = re.compile(r"^商户分期\d+/\d+:银联-")

# 转账特征关键词（方向互反的跨源配对：信用卡还款 / 提现 / 零钱通 等）
_TRANSFER_HINTS = ("还款", "提现", "零钱通", "信用卡", "银联入账", "余额宝")

# 银行来源集合（形态 3 仅在银行 ↔ 银行之间启用；新增银行 importer 时同步维护）
_BANK_SOURCE_TYPES = frozenset({"BOC", "CCB", "BANK"})

# 转账入账标记（形态 3 收入侧判据：确认收入行是「转账入账」而非当天退款/返现）
_TRANSFER_IN_MARKERS = ("银联入账", "还款", "汇款", "转入", "提现")

# 付款账户/卡号（≥8 位连续数字才视为卡号；取尾 4 位做跨行转账对关联）
_CARD_NUMBER_RE = re.compile(r"\d{8,}")

# 跨源日期容差：银行记账日可能比钱包账单的交易日晚 0–1 天（银行账单自带说明）
_CROSS_SOURCE_DATE_WINDOW = 1


def strip_channel_prefix(merchant: str) -> str:
    """剥离商户名里的支付渠道前缀（可叠乘：财付通-微信支付-测试联通 → 测试联通）。"""
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
    Layer 4  跨源匹配（CROSS_SOURCE）       -> POSSIBLE_DUPLICATE（同一笔业务
             被两张账单各记一次：银行 ↔ 支付宝/微信、银行 ↔ 银行转账对；
             只标记为疑似，裁决权留给人，绝不自动跳过）
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
    def _txn_view(t: Transaction) -> Dict:
        """Transaction ORM → 跨源谓词的行视图（与 norm.model_dump() 同键集）。"""
        return {
            "date": t.date,
            "amount": t.amount,
            "direction": t.direction,
            "merchant": t.merchant,
            "description": t.description,
            "counterparty": t.counterparty,
            "payment_method": t.payment_method,
            "source_type": t.source_type,
        }

    @staticmethod
    def _transfer_hinted(*texts) -> bool:
        joined = " ".join(str(t or "") for t in texts)
        return any(h in joined for h in _TRANSFER_HINTS)

    @classmethod
    def _view_hinted(cls, v: Dict) -> bool:
        return cls._transfer_hinted(v.get("merchant"), v.get("description"), v.get("counterparty"))

    @staticmethod
    def _bank_transfer_linked(a: Dict, b: Dict, dir_a: str, dir_b: str) -> bool:
        """形态 3：银行 ↔ 银行转账对（借记卡还款进信用卡等）。

        生产实测形态：支出侧（借记卡流水）只有对方账户名（人名），无任何转账
        关键词；收入侧（信用卡账单）文本形如「银联入账 <付款人> <付款卡尾4>」。
        关联证据（满足其一即疑似）：
        a. 支出侧付款卡尾 4 位出现在收入侧文本中（银联入账消息自带付款卡尾）
        b. 支出侧人名出现在收入侧文本中，且收入侧含转账入账标记
           （入账标记用于排除「当天消费 + 当天退款」这类同商户互反对的误配）
        """
        if (a.get("source_type") or "").upper() not in _BANK_SOURCE_TYPES:
            return False
        if (b.get("source_type") or "").upper() not in _BANK_SOURCE_TYPES:
            return False
        if dir_a == "支出" and dir_b == "收入":
            exp, inc = a, b
        elif dir_a == "收入" and dir_b == "支出":
            exp, inc = b, a
        else:
            return False
        inc_texts = " ".join(
            str(inc.get(k) or "") for k in ("merchant", "description", "counterparty")
        ).strip()
        if not inc_texts:
            return False
        # 证据 a：付款卡尾 4 位（收入侧文本里出现支出侧卡号尾 4 位）
        m = _CARD_NUMBER_RE.search(str(exp.get("payment_method") or ""))
        if m and m.group(0)[-4:] in inc_texts:
            return True
        # 证据 b：支出侧人名 + 收入侧转账入账标记
        name = str(exp.get("counterparty") or "").strip() or str(exp.get("merchant") or "").strip()
        if (
            2 <= len(name) <= 12
            and any("\u4e00" <= ch <= "\u9fff" for ch in name)
            and any(marker in inc_texts for marker in _TRANSFER_IN_MARKERS)
            and name in inc_texts
        ):
            return True
        return False

    def is_cross_source_pair(self, a: Dict, b: Dict) -> bool:
        """两行是否构成跨源重复对（Layer 4 证据谓词，纯逻辑、无 DB 访问）。

        行视图字段：date / amount / direction / merchant / description /
        counterparty / payment_method / source_type。导入时的
        find_cross_source_match 与存量回填脚本共用本口径，保证两种路径判定一致。

        三种形态（都只标疑似，绝不自动跳过）：
        1. 同方向 + 渠道前缀剥离后商户相同 + 金额相等 + 日期差 ≤ 1 天
        2. 方向互反 + 金额相等 + 日期差 ≤ 1 天 + 双侧含转账特征关键词
        3. 方向互反 + 金额相等 + 日期差 ≤ 1 天 + 银行↔银行转账关联证据（卡尾/人名）
        """
        if (a.get("source_type") or "") == (b.get("source_type") or ""):
            return False
        try:
            if (
                Decimal(str(a.get("amount"))).quantize(Decimal("0.01"))
                != Decimal(str(b.get("amount"))).quantize(Decimal("0.01"))
            ):
                return False
        except Exception:
            return False
        try:
            date_a = datetime.strptime(str(a.get("date") or ""), "%Y-%m-%d").date()
            date_b = datetime.strptime(str(b.get("date") or ""), "%Y-%m-%d").date()
        except ValueError:
            return False
        if abs((date_a - date_b).days) > _CROSS_SOURCE_DATE_WINDOW:
            return False
        dir_a = str(a.get("direction") or "支出")
        dir_b = str(b.get("direction") or "支出")
        if dir_a == dir_b:
            # 形态 1：同方向 + 商户名（剥离渠道前缀后）相同
            m_a = strip_channel_prefix(str(a.get("merchant") or ""))
            return bool(m_a) and m_a == strip_channel_prefix(str(b.get("merchant") or ""))
        # 方向互反：形态 2（双侧转账特征）或形态 3（银行↔银行关联证据）
        if self._view_hinted(a) and self._view_hinted(b):
            return True
        return self._bank_transfer_linked(a, b, dir_a, dir_b)

    def find_cross_source_match(
        self, db: Session, norm: Dict, source_type: str
    ) -> Optional[Transaction]:
        """跨源匹配：不同来源的账单对同一笔业务的重复记录。

        判定口径见 is_cross_source_pair（三种形态）；本方法只负责圈定候选
        （日期窗 + 未裁决状态 + 异源）再逐一过谓词，返回首个命中的交易。

        已知盲区（由规则引擎/人工兜底）：银行侧通用行（如「财付通-扫二维码付款」
        无真实商户名）、金额被手续费拆分的、日期差超过容差的。
        """
        try:
            new_date = datetime.strptime(str(norm.get("date") or ""), "%Y-%m-%d").date()
        except ValueError:
            return None
        lo = (new_date - timedelta(days=_CROSS_SOURCE_DATE_WINDOW)).isoformat()
        hi = (new_date + timedelta(days=_CROSS_SOURCE_DATE_WINDOW)).isoformat()
        candidates = (
            db.query(Transaction)
            .filter(
                Transaction.date >= lo,
                Transaction.date <= hi,
                Transaction.status.in_(["REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED"]),
            )
            .all()
        )
        new_view = dict(norm)
        new_view["source_type"] = source_type
        for t in candidates:
            if (t.source_type or "") == (source_type or ""):
                continue  # 跨源匹配只在不同来源之间
            if self.is_cross_source_pair(new_view, self._txn_view(t)):
                return t
        return None

    def check(self, source_id: str, raw_data: Dict, norm: Dict) -> str:
        """兼容旧签名：内存内比对，仅返回 raw hash 与 fingerprint 计算结果。
        真正去重请使用 check_against_db()。"""
        if source_id:
            return "UNIQUE"
        return "UNIQUE"
