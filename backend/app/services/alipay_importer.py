import csv
from typing import Dict, List

from app.core.utils import parse_decimal
from app.services.importer import BaseImporter, ImporterRegistry, NormalizedTransaction


class AlipayImporter(BaseImporter):
    name = "alipay"

    def detect(self, raw_data: Dict) -> bool:
        # 真实支付宝 CSV 表头（GBK 编码导出）：交易时间/交易分类/交易对方/交易订单号...
        # 历史测试 fixture 使用「交易号」，两者都接受
        keys = set(raw_data.keys())
        return "交易时间" in keys and "交易订单号" in keys and "收/支" in keys or "交易号" in keys

    def parse(self, file_path: str) -> List[Dict]:
        for encoding in ("utf-8-sig", "gbk"):
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return list(csv.DictReader(f))
            except UnicodeDecodeError:
                continue
        raise ValueError("无法读取文件：不支持的编码（尝试了 UTF-8 和 GBK）")

    def normalize(self, raw_data: Dict) -> NormalizedTransaction:
        ts = raw_data.get("交易时间", "1970-01-01")
        # 真实账单时间格式：2026/6/30 22:27（无秒、斜杠分隔）；fixture：2026-09-08 10:00:00
        date_part, _, time_part = ts.partition(" ")
        # 统一日期为 YYYY-MM-DD
        try:
            y, m, d = date_part.replace("/", "-").split("-")
            if len(m) == 1:
                m = f"0{m}"
            if len(d) == 1:
                d = f"0{d}"
            date_norm = f"{y}-{m}-{d}"
        except ValueError:
            date_norm = date_part
        source_id = raw_data.get("交易订单号") or raw_data.get("交易号") or ""
        amount = parse_decimal(raw_data.get("金额", "0"))
        direction = raw_data.get("收/支", "不计收支")
        return NormalizedTransaction(
            source_transaction_id=str(source_id).strip(),
            date=date_norm,
            time=time_part,
            amount=amount,
            currency="CNY",
            direction=direction,
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
