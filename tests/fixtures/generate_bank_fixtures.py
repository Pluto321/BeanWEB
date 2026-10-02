"""生成银行账单 PDF 测试 fixture（合成数据，无任何真实账户/交易信息）。

运行：.venv/Scripts/python.exe tests/fixtures/generate_bank_fixtures.py
产出：tests/fixtures/boc_sample.pdf（中国银行借记卡流水）
      tests/fixtures/ccb_sample.pdf（建设银行信用卡对账单）

- 使用 reportlab 内置 CID 字体 STSong-Light，无需系统字体文件，跨平台可复现
- 表格带网格线，确保 pdfplumber 能按表格结构提取
- CCB fixture 用单行合并单元格（<br/> 多行）模拟真实账单「无行间横线」的提取形态
"""
import os

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
STYLE = ParagraphStyle("t", fontName="STSong-Light", fontSize=7, leading=9)


def cell(s: str):
    return Paragraph(s.replace("\n", "<br/>"), STYLE)


def build_boc(path: str):
    headers = ["记账日期", "记账时间", "币别", "金额", "余额", "交易名称", "渠道",
               "网点名称", "附言", "对方账户名", "对方卡号/账号", "对方开户行"]
    rows = [
        headers,
        ["2025-12-31", "09:28:03", "人民币", "-23.00", "5,170.61", "网上快捷支付", "银企对接",
         "-------------------", "财付通-测试超市", "财付通-测试超市", "Z2004944000010N", "-------------------"],
        ["2025-12-30", "08:00:00", "人民币", "-47.00", "5,193.61", "网上快捷支付", "银企对接",
         "-------------------", "财付通-扫二维码付款", "财付通-扫二维码付款", "Z2004944000010N", "-------------------"],
        ["2025-12-23", "10:00:00", "人民币", "+5,000.00", "5,240.61", "银联入账", "卡组织线上/无",
         "-------------------", "----------", "测试转入人", "6230580000001234", "测试银行"],
    ]
    widths = [46, 46, 34, 42, 44, 62, 54, 56, 96, 96, 68, 58]
    table = Table([[cell(c) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, "grey")]))
    doc = SimpleDocTemplate(path, pagesize=landscape(A4))
    story = [
        Paragraph("中国银行借记卡交易流水明细单", ParagraphStyle(
            "h", fontName="STSong-Light", fontSize=12, leading=16)),
        Paragraph("借记卡号： 6217000000001234", ParagraphStyle(
            "m", fontName="STSong-Light", fontSize=8, leading=12)),
        table,
    ]
    doc.build(story)


def build_ccb(path: str):
    headers = ["序号\nNo.", "交易日\nT-Date", "银行记账日\nP-Date", "卡号后四位\nCard Number",
               "交易描述\nDescription", "交易币/金额\nTrans.Curr/Amt", "结算币/金额\nSett.Curr/Amt"]
    # 真实 CCB 账单表格无行间横线：pdfplumber 会把整段提取为一个 \n 合并单元格，这里如实模拟
    merged = [
        ["1\n2\n3",
         "20251201\n20251202\n20251205",
         "20251201\n20251203\n20251205",
         "6207\n6207\n6207",
         "京东支付-测试商户\n财付通-测试平台商户\n银联入账 测试还款人 3452",
         "人民币元/20.80\n人民币元/500.00\n人民币元/-1,426.60",
         "人民币元/20.80\n人民币元/500.00\n人民币元/-1,426.60"],
    ]
    widths = [40, 52, 58, 62, 150, 84, 84]
    table = Table([[cell(c) for c in r] for r in ([headers] + merged)], colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, "grey")]))
    doc = SimpleDocTemplate(path, pagesize=landscape(A4))
    story = [
        Paragraph("中国建设银行龙卡信用卡对账单明细", ParagraphStyle(
            "h", fontName="STSong-Light", fontSize=12, leading=16)),
        Paragraph("Credit Card Transaction Details", ParagraphStyle(
            "e", fontName="Helvetica", fontSize=9, leading=12)),
        table,
    ]
    doc.build(story)


if __name__ == "__main__":
    boc = os.path.join(HERE, "boc_sample.pdf")
    ccb = os.path.join(HERE, "ccb_sample.pdf")
    build_boc(boc)
    build_ccb(ccb)
    print("generated:", boc)
    print("generated:", ccb)
