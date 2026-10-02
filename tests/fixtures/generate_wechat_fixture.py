"""生成微信账单 xlsx 测试 fixture（合成数据，无任何真实账户/交易信息）。

运行：.venv/Scripts/python.exe tests/fixtures/generate_wechat_fixture.py
产出：tests/fixtures/wechat_sample.xlsx

- 交易时间写 datetime 对象（还原真实账单的日期单元格形态）
- 金额写数值型（float/int），还原真实账单的数值单元格形态
- 收入行支付方式为 '/'、状态「已存入测试零钱」——覆盖 payment_method 兜底路径
"""
import os
from datetime import datetime

from openpyxl import Workbook

HERE = os.path.dirname(os.path.abspath(__file__))

HEADERS = ["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)",
           "支付方式", "当前状态", "交易单号", "商户单号", "备注"]

ROWS = [
    [datetime(2026, 2, 1, 22, 23, 15), "商户消费", "测试餐饮店", "测试餐饮店-消费",
     "支出", 9.82, "测试银行信用卡(9042)", "支付成功", "4200000000WTEST0001", "WTESTMCH0001", "/"],
    [datetime(2026, 2, 6, 8, 53, 32), "扫二维码付款", "测试早点铺", "收款方备注:二维码收款",
     "支出", 7, "测试银行储蓄卡(1234)", "已转账", "5311000000WTEST0002", "/", "/"],
    [datetime(2026, 2, 8, 20, 44, 44), "转账", "测试收款人", "转账备注:微信转账",
     "收入", 2000, "/", "已存入零钱", "1000050000WTEST0003", "/", "/"],
]


def build(path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(HEADERS)
    for r in ROWS:
        ws.append(r)
    wb.save(path)


if __name__ == "__main__":
    out = os.path.join(HERE, "wechat_sample.xlsx")
    build(out)
    print("generated:", out)
