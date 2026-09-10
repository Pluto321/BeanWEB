import csv
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, List

from pydantic import BaseModel


class NormalizedTransaction(BaseModel):
    source_transaction_id: str
    date: str
    time: str = ""
    amount: Decimal
    currency: str = "CNY"
    direction: str = "支出"
    transaction_type: str = ""
    merchant: str = ""
    description: str = ""
    payment_method: str = ""
    counterparty: str = ""


class BaseImporter(ABC):
    name: str = "unknown"

    @abstractmethod
    def detect(self, raw_data: Dict) -> bool: ...

    @abstractmethod
    def parse(self, file_path: str) -> List[Dict]: ...

    @abstractmethod
    def normalize(self, raw_data: Dict) -> NormalizedTransaction: ...


class ImporterRegistry:
    _importers: List[BaseImporter] = []

    @classmethod
    def register(cls, importer: BaseImporter):
        cls._importers.append(importer)

    @classmethod
    def get_importer(cls, file_path: str) -> BaseImporter:
        """用文件首行真实内容匹配 Importer，而不是依赖文件名。
        依次尝试常见编码（UTF-8 / GBK），以实际能正确解码的为准。"""
        for encoding in ("utf-8-sig", "gbk"):
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    first_line = f.readline()
                break
            except UnicodeDecodeError:
                continue
        else:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                first_line = f.readline()
        headers = [h.strip() for h in first_line.strip().split(",") if h.strip()]
        for imp in cls._importers:
            if imp.detect({h: "" for h in headers}):
                return imp
        raise ValueError("无法识别账单来源：没有任何 Importer 能处理此文件")
