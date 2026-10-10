"""Layer 4 跨源匹配测试：同一笔业务被两张账单各记一次的疑似标记。

契约：只标记为 POSSIBLE_DUPLICATE（reason=CROSS_SOURCE），绝不自动跳过——裁决权在人。
形态 1：同方向 + 渠道前缀剥离后商户相同 + 金额相等 + 日期差 ≤1 天（钱包代付）
形态 2：方向互反 + 金额相等 + 日期差 ≤1 天 + 双侧转账特征（信用卡还款/提现）
形态 3：方向互反 + 金额相等 + 日期差 ≤1 天 + 银行↔银行关联证据（卡尾/人名+入账标记）
        （借记卡还款进信用卡：支出侧只有人名无关键词，gap #6 生产实测形态）
"""
import asyncio
import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

import app.services.alipay_importer  # noqa: F401  注册 alipay/bank
import app.services.bank_importers  # noqa: F401  注册 boc/ccb
from app.api.imports import analyze_import, commit_import
from app.models.models import Base, Transaction
from app.services.deduplication import DeduplicationService, strip_channel_prefix
from app.services.importer import ImporterRegistry

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
BOC_PDF = os.path.join(FIXTURE_DIR, "boc_sample.pdf")
CCB_PDF = os.path.join(FIXTURE_DIR, "ccb_sample.pdf")

svc = DeduplicationService()


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _norm(date, amount, direction="支出", merchant="", description="", counterparty="",
          payment_method=""):
    return {
        "date": date, "amount": Decimal(amount), "currency": "CNY",
        "direction": direction, "merchant": merchant,
        "description": description, "counterparty": counterparty,
        "payment_method": payment_method,
    }


def _txn(db, date, amount, direction="支出", merchant="", description="",
         counterparty="", payment_method="", source_type="ALIPAY", status="CONFIRMED"):
    t = Transaction(date=date, amount=amount, direction=direction, merchant=merchant,
                    description=description, counterparty=counterparty,
                    payment_method=payment_method, source_type=source_type, status=status)
    db.add(t)
    db.commit()
    return t


# ---------- 渠道前缀剥离 ----------

def test_strip_channel_prefix():
    assert strip_channel_prefix("财付通-测试超市") == "测试超市"
    assert strip_channel_prefix("财付通-微信支付-测试联通") == "测试联通"          # 叠乘剥离
    assert strip_channel_prefix("商户分期9/12:银联-北京京东世纪") == "北京京东世纪"  # 分期行
    assert strip_channel_prefix("测试超市") == "测试超市"                      # 无前缀原样
    assert strip_channel_prefix("") == ""
    assert strip_channel_prefix(None) == ""


# ---------- 形态 1：钱包代付（同方向 + 商户剥离后相同） ----------

def test_wallet_payment_cross_source_hit(db_session):
    """支付宝记「测试超市」/ 银行记「财付通-测试超市」，记账日晚一天 → 命中"""
    existing = _txn(db_session, "2025-12-30", "23.00", merchant="测试超市", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-测试超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is existing


def test_date_beyond_window_no_match(db_session):
    _txn(db_session, "2025-12-27", "23.00", merchant="测试超市", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-测试超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None  # 差 4 天


def test_different_merchant_no_match(db_session):
    _txn(db_session, "2025-12-31", "23.00", merchant="测试超市", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-美团外卖")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_empty_merchant_no_match(db_session):
    """空商户名不做形态 1 匹配（防止通用行/缺失行互相误配）"""
    _txn(db_session, "2025-12-31", "23.00", merchant="", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_same_source_no_match(db_session):
    """跨源匹配只在不同来源之间生效"""
    _txn(db_session, "2025-12-31", "23.00", merchant="财付通-测试超市", source_type="BOC")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-测试超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_ignored_txn_not_candidate(db_session):
    """IGNORED 交易不作为候选（用户已裁决忽略的记录不再干扰新导入）"""
    _txn(db_session, "2025-12-31", "23.00", merchant="测试超市", status="IGNORED")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-测试超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


# ---------- 形态 2：方向互反的转账对（还款/提现） ----------

def test_credit_card_repayment_pair(db_session):
    """信用卡还款：银行侧支出「测试信用卡中心还款业务」+ 信用卡侧收入「银联入账」"""
    existing = _txn(db_session, "2025-12-10", "1426.60",
                    merchant="测试信用卡中心还款业务", source_type="BOC")
    norm = _norm("2025-12-10", "1426.60", direction="收入",
                 merchant="银联入账 收款人 1111", description="银联入账 收款人 1111")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is existing


def test_inverted_direction_without_hints_no_match(db_session):
    """方向互反但双侧无转账特征 → 不命中（避免无关收支被误配）"""
    _txn(db_session, "2025-12-10", "1426.60", merchant="某超市", source_type="BOC")
    norm = _norm("2025-12-10", "1426.60", direction="收入", merchant="工资", description="12月工资")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is None


# ---------- 形态 3：银行 ↔ 银行转账对（支出侧裸人名，无转账关键词） ----------
# 注意：合成人名用「收款人」（隐私映射），不能用「测试还款人」——后者含关键词
# 「还款」会让形态 2 提前命中，测不到形态 3 的关联证据路径。

def test_bank_repayment_pair_by_name_and_tail(db_session):
    """借记卡还款进信用卡（gap #6 生产实测形态）：BOC 支出行只有人名无任何
    转账关键词，CCB 信用卡收入行「银联入账 <付款人> <付款卡尾4>」→ 命中"""
    existing = _txn(db_session, "2025-12-10", "1426.60", merchant="收款人",
                    counterparty="收款人", payment_method="6217000000001111",
                    source_type="BOC", status="REVIEW_REQUIRED")
    norm = _norm("2025-12-10", "1426.60", direction="收入",
                 merchant="银联入账 收款人 1111", description="银联入账 收款人 1111")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is existing


def test_bank_repayment_pair_reverse_import_order(db_session):
    """反向导入：先有 CCB 信用卡收入行，再来 BOC 支出行 → 同样命中（谓词与方向无关）"""
    existing = _txn(db_session, "2025-12-10", "1426.60", direction="收入",
                    merchant="银联入账 收款人 1111",
                    description="银联入账 收款人 1111",
                    source_type="CCB", status="REVIEW_REQUIRED")
    norm = _norm("2025-12-10", "1426.60", merchant="收款人",
                 counterparty="收款人", payment_method="6217000000001111")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is existing


def test_bank_pair_card_tail_without_in_marker(db_session):
    """证据 a：收入侧文本无转账入账标记，但含支出侧付款卡尾 4 位 → 仍命中"""
    _txn(db_session, "2025-12-10", "1426.60", merchant="收款人",
         counterparty="收款人", payment_method="6217000000001111",
         source_type="BOC", status="REVIEW_REQUIRED")
    norm = _norm("2025-12-10", "1426.60", direction="收入", merchant="收款人 1111")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is not None


def test_bank_pair_name_without_in_marker_no_match(db_session):
    """证据 b 缺入账标记不命中：排除「当天消费 + 当天退款」这类同商户互反对的误配"""
    _txn(db_session, "2025-12-10", "100.00", merchant="测试超市",
         counterparty="测试超市", payment_method="6217000000001234",
         source_type="BOC", status="REVIEW_REQUIRED")
    norm = _norm("2025-12-10", "100.00", direction="收入", merchant="退款 测试超市")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is None


def test_bank_pair_wallet_side_excluded(db_session):
    """形态 3 仅限银行 ↔ 银行：钱包一侧不适用（银行 ↔ 钱包仍走形态 1/2）"""
    _txn(db_session, "2025-12-10", "1426.60", direction="收入",
         merchant="银联入账 收款人 1111", source_type="ALIPAY")
    norm = _norm("2025-12-10", "1426.60", merchant="收款人",
                 counterparty="收款人", payment_method="6217000000001111")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_bank_pair_date_beyond_window_no_match(db_session):
    """形态 3 同样受日期窗约束（±1 天）：SQL 候选与谓词直查都判否"""
    _txn(db_session, "2025-12-05", "1426.60", merchant="收款人",
         counterparty="收款人", payment_method="6217000000001111",
         source_type="BOC", status="REVIEW_REQUIRED")
    norm = _norm("2025-12-10", "1426.60", direction="收入",
                 merchant="银联入账 收款人 1111")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is None
    a = {**norm, "source_type": "CCB"}
    b = {"date": "2025-12-05", "amount": "1426.60", "direction": "支出",
         "merchant": "收款人", "counterparty": "收款人",
         "payment_method": "6217000000001111", "source_type": "BOC"}
    assert svc.is_cross_source_pair(a, b) is False


# ---------- is_cross_source_pair 谓词（导入时与存量回填共用口径） ----------

def test_is_cross_source_pair_symmetric():
    a = {"date": "2025-12-10", "amount": "1426.60", "direction": "支出",
         "merchant": "收款人", "description": "", "counterparty": "收款人",
         "payment_method": "6217000000001111", "source_type": "BOC"}
    b = {"date": "2025-12-10", "amount": "1426.60", "direction": "收入",
         "merchant": "银联入账 收款人 1111", "description": "银联入账 收款人 1111",
         "counterparty": "", "payment_method": "建设银行信用卡2222", "source_type": "CCB"}
    assert svc.is_cross_source_pair(a, b) is True
    assert svc.is_cross_source_pair(b, a) is True                    # 参数顺序无关
    assert svc.is_cross_source_pair(a, {**b, "source_type": "BOC"}) is False  # 同源不判
    assert svc.is_cross_source_pair(a, {**b, "amount": "1426.61"}) is False   # 金额不等
    assert svc.is_cross_source_pair(a, {**b, "amount": "1426.6"}) is True     # 数值相等即等


# ---------- 集成：analyze → commit 全链路标记 ----------

def test_commit_flags_cross_source_duplicate(db_session, tmp_path, monkeypatch):
    """预置支付宝侧交易后导入 BOC fixture：命中行标 POSSIBLE_DUPLICATE/CROSS_SOURCE，
    duplicate_reason 落库（drawer「重复提示」字段），其余行正常创建。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "raw"))

    _txn(db_session, "2025-12-31", "23.00", merchant="测试超市", source_type="ALIPAY")

    with open(BOC_PDF, "rb") as f:
        up = UploadFile(f, filename="boc_sample.pdf")
        result = asyncio.run(analyze_import(up, db_session))
    assert result["stats"]["possible_duplicate"] == 1
    assert result["duplicates"][0]["reason"] == "CROSS_SOURCE"
    assert result["duplicates"][0]["row_number"] == 1
    # 行级明细：命中行 kind=possible_duplicate 且带 reason，其余行为 new
    kinds = {r["row_number"]: r["kind"] for r in result["rows"]}
    assert kinds == {1: "possible_duplicate", 2: "new", 3: "new"}
    assert result["rows"][0]["reason"] == "CROSS_SOURCE"

    commit_import(result["import_id"], db_session)
    flagged = (db_session.query(Transaction)
               .filter(Transaction.status == "POSSIBLE_DUPLICATE").all())
    assert len(flagged) == 1
    assert flagged[0].duplicate_reason == "CROSS_SOURCE"
    assert flagged[0].direction == "支出" and flagged[0].amount == "23.00"
    # 其余两行正常创建（47 元扫码 + 5000 元收入），不受跨源标记影响
    boc_txns = db_session.query(Transaction).filter(Transaction.source_type == "BOC").all()
    assert len(boc_txns) == 3
    assert {t.status for t in boc_txns if t.direction == "支出"} == {"POSSIBLE_DUPLICATE", "REVIEW_REQUIRED"}


def test_commit_flags_bank_pair_cross_source(db_session, tmp_path, monkeypatch):
    """预置 BOC 支出（裸人名 + 借记卡号）后导入 CCB fixture：
    「银联入账 测试还款人 1111」收入行标 POSSIBLE_DUPLICATE/CROSS_SOURCE
    （duplicate_reason 落库），先导入的 BOC 侧保持 REVIEW_REQUIRED 不动
    （导入时只标后到的一侧，裁决权在人）。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "raw"))

    _txn(db_session, "2025-12-05", "1426.60", merchant="收款人",
         counterparty="收款人", payment_method="6217000000001111",
         source_type="BOC", status="REVIEW_REQUIRED")

    with open(CCB_PDF, "rb") as f:
        up = UploadFile(f, filename="ccb_sample.pdf")
        result = asyncio.run(analyze_import(up, db_session))
    assert result["stats"]["possible_duplicate"] == 1
    assert result["duplicates"][0]["reason"] == "CROSS_SOURCE"
    assert result["duplicates"][0]["row_number"] == 3
    kinds = {r["row_number"]: r["kind"] for r in result["rows"]}
    assert kinds == {1: "new", 2: "new", 3: "possible_duplicate"}

    commit_import(result["import_id"], db_session)
    flagged = (db_session.query(Transaction)
               .filter(Transaction.status == "POSSIBLE_DUPLICATE").all())
    assert len(flagged) == 1
    assert flagged[0].duplicate_reason == "CROSS_SOURCE"
    assert flagged[0].direction == "收入" and flagged[0].amount == "1426.60"
    assert flagged[0].merchant == "银联入账 测试还款人 1111"
    boc = db_session.query(Transaction).filter(Transaction.source_type == "BOC").one()
    assert boc.status == "REVIEW_REQUIRED" and boc.duplicate_reason is None
