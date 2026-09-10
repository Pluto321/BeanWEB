import hashlib
import json
from decimal import Decimal
from typing import Dict

class DeduplicationService:
    def get_canonical_fingerprint(self, norm: Dict) -> str:
        # 使用规范化数据，保证字段顺序和类型稳定
        data = {
            "source": norm.get("source"),
            "date": str(norm.get("date")),
            "amount": str(norm.get("amount").quantize(Decimal("0.01"))),
            "currency": norm.get("currency"),
            "direction": norm.get("direction"),
            "counterparty": norm.get("counterparty"),
            "merchant": norm.get("merchant")
        }
        # 强制排序，确保生成稳定的哈希
        stable_json = json.dumps(data, sort_keys=True)
        return hashlib.sha256(stable_json.encode()).hexdigest()

    def check(self, source_id: str, raw_data: Dict, norm: Dict) -> str:
        # 实现层级检查
        # 1. source_transaction_id -> EXACT_DUPLICATE
        # 2. raw hash -> EXACT_DUPLICATE
        # 3. canonical -> POSSIBLE_DUPLICATE
        return "UNIQUE"
