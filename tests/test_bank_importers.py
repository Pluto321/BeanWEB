"""银行账单 PDF Importer 测试（BOC 借记卡 / CCB 信用卡）。

Fixture：tests/fixtures/boc_sample.pdf、ccb_sample.pdf（generate_bank_fixtures.py 生成的合成数据）。
真实账单冒烟：账本/ 目录（已 gitignore）存在 PDF 时自动运行，否则跳过。
所有 DB 测试用内存 SQLite，绝不触碰真实 beanweb.db。
"""
import asyncio
import glob
import os
import re
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

import app.services.alipay_importer  # noqa: F401  注册 alipay/bank
import app.services.bank_importers  # noqa: F401  注册 boc/ccb
from app.api.imports import analyze_import, commit_import, match_payment_account
from app.core.utils import parse_decimal
from app.models.models import Account, Base, Transaction, TransactionSplit
from app.services.deduplication import DeduplicationService
from app.services.importer import ImporterRegistry

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
BOC_PDF = os.path.join(FIXTURE_DIR, "boc_sample.pdf")
CCB_PDF = os.path.join(FIXTURE_DIR, "ccb_sample.pdf")
LEDGER_DIR = os.path.join(os.path.dirname(__file__), "..", "账本")


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _real_pdfs():
    if not os.path.isdir(LEDGER_DIR):
        return []
    return glob.glob(os.path.join(LEDGER_DIR, "*.pdf"))


# ---------- 注册表探测 ----------

def test_registry_detects_bank_pdf_fixtures():
    assert ImporterRegistry.get_importer(BOC_PDF).name == "boc"
    assert ImporterRegistry.get_importer(CCB_PDF).name == "ccb"


def test_registry_csv_no_regression():
    assert ImporterRegistry.get_importer(os.path.join(FIXTURE_DIR, "alipay_sample.csv")).name == "alipay"
    assert ImporterRegistry.get_importer(os.path.join(FIXTURE_DIR, "bank_sample.csv")).name == "bank"


def test_registry_rejects_unknown_file(tmp_path):
    p = tmp_path / "unknown.csv"
    p.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ImporterRegistry.get_importer(str(p))


# ---------- BOC fixture ----------

def test_boc_fixture_parse_and_normalize():
    imp = ImporterRegistry.get_importer(BOC_PDF)
    rows = imp.parse(BOC_PDF)
    assert len(rows) == 3
    norms = [imp.normalize(r) for r in rows]

    # 借记卡号从页眉注入每行，用于付款账户匹配
    assert all(n.payment_method == "6217000000001234" for n in norms)
    # 符号 → 方向；金额为正数幅值
    assert norms[0].amount == Decimal("23.00") and norms[0].direction == "支出"
    assert norms[2].amount == Decimal("5000.00") and norms[2].direction == "收入"
    # 全横线占位符清洗为空串；附言为空时商户取对方账户名
    assert norms[2].description == "" and norms[2].merchant == "测试转入人"
    assert norms[0].transaction_type == "网上快捷支付"
    assert all(n.currency == "CNY" for n in norms)
    # 合成 ID：前缀 + 确定性 + 唯一
    ids = [n.source_transaction_id for n in norms]
    assert all(i.startswith("BOC-") for i in ids)
    assert len(set(ids)) == 3
    assert [imp.normalize(r).source_transaction_id for r in imp.parse(BOC_PDF)] == ids


def test_boc_fixture_balance_continuity():
    """余额连续性是银行流水的自校验不变量：余额[i] - 金额[i] == 余额[i+1]"""
    imp = ImporterRegistry.get_importer(BOC_PDF)
    rows = imp.parse(BOC_PDF)
    for i in range(len(rows) - 1):
        assert parse_decimal(rows[i]["余额"]) - parse_decimal(rows[i]["金额"]) == parse_decimal(rows[i + 1]["余额"])


# ---------- CCB fixture ----------

def test_ccb_fixture_parse_merged_cells():
    """真实 CCB 账单表格无行间横线：pdfplumber 把多行提取为一个 \n 合并单元格，parse 负责拆开"""
    imp = ImporterRegistry.get_importer(CCB_PDF)
    rows = imp.parse(CCB_PDF)
    assert len(rows) == 3
    assert [r["序号"] for r in rows] == ["1", "2", "3"]


def test_ccb_fixture_normalize():
    imp = ImporterRegistry.get_importer(CCB_PDF)
    norms = [imp.normalize(r) for r in imp.parse(CCB_PDF)]
    # YYYYMMDD → YYYY-MM-DD
    assert norms[0].date == "2025-12-01"
    assert norms[1].date == "2025-12-02"
    # 正=刷卡支出，负=还款/退款
    assert norms[0].direction == "支出" and norms[0].amount == Decimal("20.80")
    assert norms[2].direction == "收入" and norms[2].amount == Decimal("1426.60")
    # 交易描述按首个「-」拆渠道/商户；无分隔符则整段作商户
    assert norms[0].transaction_type == "京东支付" and norms[0].merchant == "测试商户"
    assert norms[2].transaction_type == "" and norms[2].merchant == "银联入账 测试还款人 3452"
    assert all(n.payment_method == "建设银行信用卡6207" for n in norms)
    assert all(n.currency == "CNY" for n in norms)
    ids = [n.source_transaction_id for n in norms]
    assert all(i.startswith("CCB-") for i in ids)
    assert len(set(ids)) == 3


def test_ccb_rejects_misaligned_merged_cells():
    """合并单元格各列行数不一致时必须 fail-loud（拒绝静默错位导入财务数据）"""
    from app.services.bank_importers import CCBImporter
    with pytest.raises(ValueError):
        CCBImporter._split_merged_row(["1\n2", "20251201\n20251202\n20251203",
                                       "6207\n6207", "a/1.00\nb/2.00", "c/1.00\nd/2.00"])


# ---------- 付款账户匹配（Assets + Liabilities） ----------

def test_match_payment_account_assets_and_liabilities(db_session):
    db_session.add(Account(name="Assets:BOC:6217", open_date="2025-01-01", aliases=["6217000000001234"]))
    db_session.add(Account(name="Liabilities:CCB:6207", open_date="2025-01-01", aliases=["6207"]))
    db_session.commit()
    assert match_payment_account(db_session, "6217000000001234") == "Assets:BOC:6217"
    assert match_payment_account(db_session, "建设银行信用卡6207") == "Liabilities:CCB:6207"
    assert match_payment_account(db_session, "无法匹配的文本") is None
    assert match_payment_account(db_session, "") is None


# ---------- Analyze → Commit 全链路（内存 DB + 临时存储） ----------

def test_analyze_commit_roundtrip(db_session, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "raw"))

    with open(BOC_PDF, "rb") as f:
        up = UploadFile(f, filename="boc_sample.pdf")
        result = asyncio.run(analyze_import(up, db_session))

    assert result["parser"] == "boc"
    assert result["batch_status"] == "PENDING_ANALYZED"
    assert result["stats"] == {"total": 3, "new": 3, "existing": 0, "possible_duplicate": 0, "invalid": 0}

    batch_id = result["import_id"]
    committed = commit_import(batch_id, db_session)
    assert committed["status"] == "COMPLETED"
    assert committed["created"] == 3

    txns = db_session.query(Transaction).all()
    assert len(txns) == 3

    income = [t for t in txns if t.direction == "收入"]
    assert len(income) == 1
    by_role = {s.role: s for s in income[0].splits}
    assert by_role["expense"].account == "Income:BeanWEB"      # 收入分类腿用默认收入账户
    assert by_role["payment"].account == "Assets:BeanWEB"     # 无别名匹配 → 默认资产账户
    assert parse_decimal(by_role["payment"].amount) == Decimal("5000.00")  # 收入 payment 腿为正

    expense = [t for t in txns if t.direction == "支出"][0]
    erole = {s.role: s for s in expense.splits}
    assert erole["expense"].account == "Expenses:Uncategorized"
    assert parse_decimal(erole["payment"].amount) == Decimal("-23.00")      # 支出 payment 腿为负

    # 幂等：重复 commit → 409
    with pytest.raises(HTTPException) as exc:
        commit_import(batch_id, db_session)
    assert exc.value.status_code == 409

    # 同文件重复分析：文件级去重 + 交易级 EXACT_DUPLICATE（合成 ID 稳定）
    with open(BOC_PDF, "rb") as f:
        up2 = UploadFile(f, filename="boc_sample.pdf")
        result2 = asyncio.run(analyze_import(up2, db_session))
    assert result2["stats"]["total"] == 3
    assert result2["stats"]["existing"] == 3
    assert result2["stats"]["new"] == 0
    assert result2["stats"]["invalid"] == 0


# ---------- 真实账单冒烟（账本/ 已 gitignore，仅本地存在时运行） ----------

@pytest.mark.skipif(not _real_pdfs(), reason="账本/ 下没有真实银行账单（已 gitignore）")
def test_real_statements_parse_and_normalize():
    for path in _real_pdfs():
        imp = ImporterRegistry.get_importer(path)
        assert imp.name in ("boc", "ccb")
        rows = imp.parse(path)
        assert rows
        norms = [imp.normalize(r) for r in rows]
        ids = [n.source_transaction_id for n in norms]
        assert len(ids) == len(set(ids))
        for n in norms:
            assert n.amount > 0
            assert n.direction in ("支出", "收入", "不计收支")
            assert n.currency == "CNY"


@pytest.mark.skipif(not _real_pdfs(), reason="账本/ 下没有真实银行账单（已 gitignore）")
def test_real_boc_balance_continuity():
    boc = None
    for path in _real_pdfs():
        if ImporterRegistry.get_importer(path).name == "boc":
            boc = path
            break
    if boc is None:
        pytest.skip("账本/ 下没有中国银行账单")
    rows = ImporterRegistry.get_importer(boc).parse(boc)
    for i in range(len(rows) - 1):
        assert parse_decimal(rows[i]["余额"]) - parse_decimal(rows[i]["金额"]) == parse_decimal(rows[i + 1]["余额"])


# ---------- 审计回归：金额符号 → confirm → export → Beancount 方向 ----------

_POSTING_RE = re.compile(r"^\s+(\S+)\s+(-?\d[\d,]*\.\d{2})\s+CNY\s*$", re.MULTILINE)


def _postings(content: str) -> dict:
    """从 .bean fragment 提取 account -> 金额（单腿账户场景）。"""
    return {m.group(1): Decimal(m.group(2).replace(",", "")) for m in _POSTING_RE.finditer(content)}


def _confirm_and_export(db_session, txn_id, tmp_path, monkeypatch) -> str:
    from app.core.config import settings
    from app.services.export_service import ExportService
    from app.services.review import ReviewService
    # 每笔交易独立 ledger 目录：write_fragment 按月追加，同月多笔导出会写入同一 fragment
    monkeypatch.setattr(settings, "LEDGER_DIR", str(tmp_path / f"ledgers-{txn_id}"))
    ReviewService.set_status(db_session, txn_id, "CONFIRMED", "audit regression")
    record = ExportService.export_transaction(db_session, txn_id)
    with open(record.file_path, encoding="utf-8") as f:
        return f.read()


def test_negative_payment_leg_exports_correct_direction(db_session, tmp_path, monkeypatch):
    """审计回归：导入生成的 payment 腿在 DB 中为负数，必须原样保留到 Beancount
    （前端 Math.abs 只影响编辑器展示/校验，导出始终读取 DB 真实符号）。"""
    txn = Transaction(date="2025-12-31", amount="23.00", currency="CNY", merchant="测试商户",
                     direction="支出", source_type="BOC", status="REVIEW_REQUIRED")
    db_session.add(txn)
    db_session.flush()
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Expenses:Uncategorized", amount="23.00", role="expense"))
    db_session.add(TransactionSplit(transaction_id=txn.id, account="Assets:BOC:6217", amount="-23.00", role="payment"))
    db_session.commit()

    content = _confirm_and_export(db_session, txn.id, tmp_path, monkeypatch)
    postings = _postings(content)
    assert postings == {"Expenses:Uncategorized": Decimal("23.00"), "Assets:BOC:6217": Decimal("-23.00")}
    assert sum(postings.values()) == 0, "分录必须借贷平衡"


def test_ccb_liabilities_full_path_to_beancount(db_session, tmp_path, monkeypatch):
    """审计回归：CCB 信用卡支出 → alias "6207" 匹配 Liabilities 账户 → confirm → export，
    最终分录负债账户记贷方（-金额），账户类型（Liabilities）不影响匹配。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "raw"))
    db_session.add(Account(name="Liabilities:CCB:6207", open_date="2025-01-01", aliases=["6207"]))
    db_session.commit()

    with open(CCB_PDF, "rb") as f:
        up = UploadFile(f, filename="ccb_sample.pdf")
        result = asyncio.run(analyze_import(up, db_session))
    commit_import(result["import_id"], db_session)

    txn = (db_session.query(Transaction)
           .filter(Transaction.direction == "支出", Transaction.source_type == "CCB")
           .first())
    by_role = {s.role: s for s in txn.splits}
    assert by_role["payment"].account == "Liabilities:CCB:6207"
    assert parse_decimal(by_role["payment"].amount) == Decimal("-20.80")

    content = _confirm_and_export(db_session, txn.id, tmp_path, monkeypatch)
    postings = _postings(content)
    assert postings == {"Expenses:Uncategorized": Decimal("20.80"), "Liabilities:CCB:6207": Decimal("-20.80")}
    assert sum(postings.values()) == 0, "分录必须借贷平衡"


def test_income_and_expense_category_export_regression(db_session, tmp_path, monkeypatch):
    """审计回归：收入分类腿 = Income:BeanWEB（导出为贷方负数），支出仍走规则引擎默认
    Expenses:Uncategorized；Bank Importer 与 CSV importer 共用同一条 commit 路径。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "raw"))
    with open(BOC_PDF, "rb") as f:
        up = UploadFile(f, filename="boc_sample.pdf")
        result = asyncio.run(analyze_import(up, db_session))
    commit_import(result["import_id"], db_session)

    txns = db_session.query(Transaction).all()
    income = next(t for t in txns if t.direction == "收入")
    expense = next(t for t in txns if t.direction == "支出")

    assert {s.role: s for s in income.splits}["expense"].account == "Income:BeanWEB"
    assert {s.role: s for s in expense.splits}["expense"].account == "Expenses:Uncategorized"

    inc_postings = _postings(_confirm_and_export(db_session, income.id, tmp_path, monkeypatch))
    assert inc_postings == {"Income:BeanWEB": Decimal("-5000.00"), "Assets:BeanWEB": Decimal("5000.00")}
    assert sum(inc_postings.values()) == 0

    exp_postings = _postings(_confirm_and_export(db_session, expense.id, tmp_path, monkeypatch))
    assert exp_postings == {"Expenses:Uncategorized": Decimal("23.00"), "Assets:BeanWEB": Decimal("-23.00")}
    assert sum(exp_postings.values()) == 0


def test_dedup_same_content_across_files(db_session):
    """审计 Case B/C：同一交易出现在不同文件。
    - BOC（合成 ID = 内容哈希）：同内容 → 同 ID → Layer1 EXACT_DUPLICATE（跨账单精确去重）
    - CCB（合成 ID 含序号）：不同导出的同一交易 → ID 不同、raw_hash 不同 →
      落 Layer3 canonical fingerprint → POSSIBLE_DUPLICATE（进人工审核，不静默重复）
    """
    dedup = DeduplicationService()

    # Case B — BOC：不同文件名/字节序，同一行内容 → 合成 ID 相同
    boc_imp = ImporterRegistry.get_importer(BOC_PDF)
    boc_row = boc_imp.parse(BOC_PDF)[0]
    boc_norm = boc_imp.normalize(boc_row)
    boc_hash = dedup.get_raw_hash(boc_row)
    boc_fp = dedup.get_canonical_fingerprint(boc_norm.model_dump())
    assert dedup.check_against_db(db_session, boc_norm.source_transaction_id, boc_hash, boc_fp) == ("UNIQUE", None)
    db_session.add(Transaction(date=boc_norm.date, amount=str(boc_norm.amount), direction=boc_norm.direction,
                               source_type="BOC", source_transaction_id=boc_norm.source_transaction_id,
                               raw_hash=boc_hash, canonical_fingerprint=boc_fp, status="CONFIRMED"))
    db_session.commit()
    result, reason = dedup.check_against_db(db_session, boc_norm.source_transaction_id, boc_hash, boc_fp)
    assert (result, reason) == ("EXACT_DUPLICATE", "SOURCE_ID")

    # Case C — CCB：同一交易、另一份导出（序号不同）→ ID/raw_hash 不同，指纹相同
    ccb_imp = ImporterRegistry.get_importer(CCB_PDF)
    ccb_row = ccb_imp.parse(CCB_PDF)[0]
    other_export = dict(ccb_row)
    other_export["序号"] = "99"
    norm_a = ccb_imp.normalize(ccb_row)
    norm_b = ccb_imp.normalize(other_export)
    assert norm_a.source_transaction_id != norm_b.source_transaction_id
    assert norm_a.amount == norm_b.amount and norm_a.date == norm_b.date and norm_a.merchant == norm_b.merchant
    fp_a = dedup.get_canonical_fingerprint(norm_a.model_dump())
    fp_b = dedup.get_canonical_fingerprint(norm_b.model_dump())
    assert fp_a == fp_b
    db_session.add(Transaction(date=norm_a.date, amount=str(norm_a.amount), direction=norm_a.direction,
                               source_type="CCB", source_transaction_id=norm_a.source_transaction_id,
                               raw_hash=dedup.get_raw_hash(ccb_row), canonical_fingerprint=fp_a, status="CONFIRMED"))
    db_session.commit()
    result, reason = dedup.check_against_db(
        db_session, norm_b.source_transaction_id, dedup.get_raw_hash(other_export), fp_b)
    assert (result, reason) == ("POSSIBLE_DUPLICATE", "CANONICAL_FINGERPRINT")
