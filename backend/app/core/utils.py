import os
from decimal import Decimal, InvalidOperation

def parse_decimal(value: str) -> Decimal:
    """
    精确解析金额字符串，移除千分位并转换为 Decimal。
    解析失败则抛出异常，防止静默财务数据损坏。
    """
    if not value or str(value).strip() == "":
        raise ValueError("金额字段不能为空")
    
    try:
        clean_value = str(value).replace(",", "").strip()
        return Decimal(clean_value)
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"金额解析失败: {value}") from e
