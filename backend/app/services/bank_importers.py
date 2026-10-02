"""真实银行账单 PDF Importer：中国银行借记卡流水 + 建设银行信用卡对账单。

设计约定（与现有 Alipay/Bank Importer 同一契约）：
- detect()：按账单表格的列名签名判断（probe dict 由 matches_file 构造）
- matches_file()：PDF 魔数校验 + pdfplumber 提取首页表格表头 → detect
- parse()：返回 List[Dict]，原样进入 RawTransaction.raw_data_json（Raw 不可变）
- normalize()：输出 NormalizedTransaction；amount 为正数幅值，方向由 direction 表达
- 银行流水无全局唯一交易号：source_transaction_id 用关键字段的稳定 sha256 短哈希合成
  （同一行重复导入 → 合成 ID 相同 → Layer1 EXACT_DUPLICATE，幂等安全）
"""
import hashlib
import re
from decimal import Decimal
from typing import Dict, List

from app.core.utils import parse_decimal
from app.services.importer import BaseImporter, ImporterRegistry, NormalizedTransaction

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_pdf(file_path: str) -> bool:
    try:
        with open(file_path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def _clean(cell) -> str:
    """单元格清洗：去换行/首尾空白；全横线占位符归一为空串。"""
    if cell is None:
        return ""
    s = str(cell).replace("\r", "").replace("\n", "").strip()
    if s and set(s) <= {"-"}:
        return ""
    return s


class BOCImporter(BaseImporter):
    """中国银行借记卡交易流水明细单（PDF）。

    表格列：记账日期|记账时间|币别|金额|余额|交易名称|渠道|网点名称|附言|对方账户名|对方卡号/账号|对方开户行
    金额带符号（负=支出、正=收入）；借记卡号在表格外的页眉文本中，parse 时注入每行。
    """

    name = "boc"
    COLUMNS = ["记账日期", "记账时间", "币别", "金额", "余额", "交易名称", "渠道",
               "网点名称", "附言", "对方账户名", "对方卡号/账号", "对方开户行"]
    REQUIRED_COLUMNS = {"记账日期", "记账时间", "金额", "交易名称", "对方账户名"}
    CURRENCY_MAP = {"人民币": "CNY", "美元": "USD", "欧元": "EUR", "英镑": "GBP", "日元": "JPY"}

    def detect(self, raw_data: Dict) -> bool:
        keys = set(raw_data.keys())
        return self.REQUIRED_COLUMNS <= keys

    def matches_file(self, file_path: str) -> bool:
        if not _is_pdf(file_path):
            return False
        import pdfplumber
        try:
            with pdfplumber.open(file_path) as pdf:
                probe = {}
                for table in pdf.pages[0].extract_tables():
                    if table and table[0]:
                        probe = {_clean(c): "" for c in table[0]}
                        break
                return self.detect(probe)
        except Exception:
            return False

    def parse(self, file_path: str) -> List[Dict]:
        import pdfplumber
        card_no = ""
        rows: List[Dict] = []
        with pdfplumber.open(file_path) as pdf:
            first_text = pdf.pages[0].extract_text() or ""
            m = re.search(r"借记卡号[：:]\s*([0-9]{13,19})", first_text)
            if m:
                card_no = m.group(1)
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        cells = [_clean(c) for c in (row or [])]
                        if not cells or not cells[0]:
                            continue
                        if cells[0] == "记账日期" or not _DATE_RE.match(cells[0]):
                            continue  # 表头行 / 非数据行
                        d = dict(zip(self.COLUMNS, cells))
                        d["借记卡号"] = card_no
                        rows.append(d)
        return rows

    def normalize(self, raw_data: Dict) -> NormalizedTransaction:
        date = (raw_data.get("记账日期") or "").strip()
        time = (raw_data.get("记账时间") or "").strip()
        raw_amount = parse_decimal(raw_data.get("金额"))
        amount = abs(raw_amount)
        direction = "支出" if raw_amount < 0 else ("收入" if raw_amount > 0 else "不计收支")
        currency_text = (raw_data.get("币别") or "").strip()
        sid_source = "|".join([
            raw_data.get("记账日期", ""), raw_data.get("记账时间", ""),
            raw_data.get("金额", ""), raw_data.get("余额", ""), raw_data.get("对方账户名", ""),
        ])
        digest = hashlib.sha256(sid_source.encode("utf-8")).hexdigest()[:16]
        return NormalizedTransaction(
            source_transaction_id=f"BOC-{digest}",
            date=date,
            time=time,
            amount=amount,
            currency=self.CURRENCY_MAP.get(currency_text, currency_text or "CNY"),
            direction=direction,
            transaction_type=(raw_data.get("交易名称") or "").strip(),
            merchant=(raw_data.get("对方账户名") or "").strip(),
            description=(raw_data.get("附言") or "").strip(),
            payment_method=(raw_data.get("借记卡号") or "").strip(),
            counterparty=(raw_data.get("对方账户名") or "").strip(),
        )


class CCBImporter(BaseImporter):
    """中国建设银行龙卡信用卡对账单明细（PDF）。

    表格列：序号|交易日|银行记账日|卡号后四位|交易描述|交易币/金额|结算币/金额
    日期 YYYYMMDD；金额形如「人民币元/20.80」，正=刷卡消费、负=还款/退款；
    表格无行间横线时 pdfplumber 会把多行并成一个单元格（\\n 分隔），parse 时拆开。
    """

    name = "ccb"
    COLUMNS = ["序号", "交易日", "银行记账日", "卡号后四位", "交易描述", "交易币/金额", "结算币/金额"]
    REQUIRED_SUBSTRINGS = ("交易日", "银行记账日", "交易描述")
    CURRENCY_MAP = {"人民币元": "CNY", "美元": "USD", "欧元": "EUR"}

    def detect(self, raw_data: Dict) -> bool:
        keys = set(raw_data.keys())
        return all(any(sub in k for k in keys) for sub in self.REQUIRED_SUBSTRINGS)

    def matches_file(self, file_path: str) -> bool:
        if not _is_pdf(file_path):
            return False
        import pdfplumber
        try:
            with pdfplumber.open(file_path) as pdf:
                probe = {}
                for table in pdf.pages[0].extract_tables():
                    if table and table[0]:
                        probe = {_clean(c): "" for c in table[0]}
                        break
                return self.detect(probe)
        except Exception:
            return False

    @staticmethod
    def _split_merged_row(cells: List[str]) -> List[Dict]:
        """把 \n 合并的多行单元格拆回逐笔行 dict。各列行数必须一致，否则拒绝
        （fail-loud：宁可报错也不静默错位导入财务数据）。"""
        cols = [c.split("\n") for c in cells]
        n = len(cols[0])
        if any(len(col) != n for col in cols):
            raise ValueError(
                f"建设银行账单解析失败：合并单元格列行数不一致（{[len(c) for c in cols]}）"
            )
        out: List[Dict] = []
        for i in range(n):
            d = dict(zip(CCBImporter.COLUMNS, [_clean(col[i]) for col in cols]))
            if any(v for v in d.values()):
                out.append(d)
        return out

    def parse(self, file_path: str) -> List[Dict]:
        import pdfplumber
        rows: List[Dict] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        cells = [str(c) if c is not None else "" for c in (row or [])]
                        if not cells or not cells[0].strip():
                            continue
                        first = cells[0].replace("\n", "").strip()
                        if first.startswith("序号"):
                            continue  # 表头行
                        if not any(c.strip() for c in cells):
                            continue
                        rows.extend(self._split_merged_row(cells))
        return rows

    def normalize(self, raw_data: Dict) -> NormalizedTransaction:
        date_raw = (raw_data.get("交易日") or "").strip()
        if not re.match(r"^\d{8}$", date_raw):
            raise ValueError(f"交易日格式不合法: {date_raw}")
        date = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        settle = (raw_data.get("结算币/金额") or "").strip() or (raw_data.get("交易币/金额") or "").strip()
        if "/" not in settle:
            raise ValueError(f"金额格式不合法: {settle}")
        currency_text, amount_text = settle.split("/", 1)
        raw_amount = parse_decimal(amount_text)
        amount = abs(raw_amount)
        direction = "支出" if raw_amount > 0 else ("收入" if raw_amount < 0 else "不计收支")
        card_last4 = (raw_data.get("卡号后四位") or "").strip()
        desc = (raw_data.get("交易描述") or "").strip()
        transaction_type, _, merchant = desc.partition("-")
        if not merchant:
            merchant = desc
            transaction_type = ""
        sid_source = "|".join([
            raw_data.get("序号", ""), raw_data.get("交易日", ""),
            raw_data.get("银行记账日", ""), card_last4, settle, desc,
        ])
        digest = hashlib.sha256(sid_source.encode("utf-8")).hexdigest()[:16]
        return NormalizedTransaction(
            source_transaction_id=f"CCB-{digest}",
            date=date,
            time="",
            amount=amount,
            currency=self.CURRENCY_MAP.get(currency_text, currency_text or "CNY"),
            direction=direction,
            transaction_type=transaction_type,
            merchant=merchant,
            description=desc,
            payment_method=f"建设银行信用卡{card_last4}",
            counterparty="",
        )


ImporterRegistry.register(BOCImporter())
ImporterRegistry.register(CCBImporter())
