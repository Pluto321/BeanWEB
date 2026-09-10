import csv
from typing import Dict, List

from app.core.utils import parse_decimal
from app.services.importer import BaseImporter, ImporterRegistry, NormalizedTransaction


class AlipayImporter(BaseImporter):
    name = "alipay"

    def detect(self, raw_data: Dict) -> bool:
        return "交易号" in raw_data

    def parse(self, file_path: str) -> List[Dict]:
        for encoding in ("utf-8-sig", "gbk"):
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return list(csv.DictReader(f))
            except UnicodeDecodeError:
                continue
        raise ValueError("无法读取文件：不支持的编码（尝试了 UTF-8 和 GBK）")

    def normalize(self, raw_data: Dict) -> NormalizedTransaction:
        ts = raw_data.get("交易时间", "1970-01-01 00:00:00")
        parts = ts.split(" ")
        return NormalizedTransaction(
            source_transaction_id=raw_data.get("交易号", ""),
            date=parts[0],
            time=parts[1] if len(parts) > 1 else "",
            amount=parse_decimal(raw_data.get("金额", "0")),
            currency="CNY",
            direction=raw_data.get("收/支", "不计收支"),
            transaction_type=raw_data.get("交易分类", ""),
            merchant=raw_data.get("交易对方", ""),
            description=raw_data.get("商品说明", ""),
            payment_method=raw_data.get("收/付款方式", ""),
            counterparty=raw_data.get("交易对方", ""),
        )


class BankImporter(BaseImporter):
    """测试用第二来源，字段结构与支付宝完全不同"""

    name = "bank"

    def detect(self, raw_data: Dict) -> bool:
        return "借方发生额" in raw_data

    def parse(self, file_path: str) -> List[Dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def normalize(self, raw_data: Dict) -> NormalizedTransaction:
        debit = (raw_data.get("借方发生额") or "").strip()
        credit = (raw_data.get("贷方发生额") or "").strip()
        is_debit = parse_decimal(debit if debit else "0") != 0
        amount = parse_decimal(debit if is_debit else (credit or "0"))
        return NormalizedTransaction(
            source_transaction_id=raw_data.get("流水号", ""),
            date=raw_data.get("交易日期", ""),
            time="00:00:00",
            amount=amount,
            currency="CNY",
            direction="支出" if is_debit else "收入",
            transaction_type="Transfer",
            merchant=raw_data.get("摘要", ""),
            description=raw_data.get("备注", ""),
            payment_method="BankCard",
            counterparty=raw_data.get("对方户名", ""),
        )


ImporterRegistry.register(AlipayImporter())
ImporterRegistry.register(BankImporter())
