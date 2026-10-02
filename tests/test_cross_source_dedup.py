"""Layer 4 跨源匹配测试：银行 ↔ 支付宝/微信 各记一次的同一笔业务。

契约：只标记为 POSSIBLE_DUPLICATE（reason=CROSS_SOURCE），绝不自动跳过——裁决权在人。
形态 1：同方向 + 渠道前缀剥离后商户相同 + 金额相等 + 日期差 ≤1 天（钱包代付）
形态 2：方向互反 + 金额相等 + 日期差 ≤1 天 + 双侧转账特征（信用卡还款/提现）
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

svc = DeduplicationService()


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _norm(date, amount, direction="支出", merchant="", description="", counterparty=""):
    return {
        "date": date, "amount": Decimal(amount), "currency": "CNY",
        "direction": direction, "merchant": merchant,
        "description": description, "counterparty": counterparty,
    }


def _txn(db, date, amount, direction="支出", merchant="", description="",
         source_type="ALIPAY", status="CONFIRMED"):
    t = Transaction(date=date, amount=amount, direction=direction, merchant=merchant,
                    description=description, source_type=source_type, status=status)
    db.add(t)
    db.commit()
    return t


# ---------- 渠道前缀剥离 ----------

def test_strip_channel_prefix():
    assert strip_channel_prefix("财付通-聚鑫福超市") == "聚鑫福超市"
    assert strip_channel_prefix("财付通-微信支付-天津联通") == "天津联通"          # 叠乘剥离
    assert strip_channel_prefix("商户分期9/12:银联-北京京东世纪") == "北京京东世纪"  # 分期行
    assert strip_channel_prefix("聚鑫福超市") == "聚鑫福超市"                      # 无前缀原样
    assert strip_channel_prefix("") == ""
    assert strip_channel_prefix(None) == ""


# ---------- 形态 1：钱包代付（同方向 + 商户剥离后相同） ----------

def test_wallet_payment_cross_source_hit(db_session):
    """支付宝记「聚鑫福超市」/ 银行记「财付通-聚鑫福超市」，记账日晚一天 → 命中"""
    existing = _txn(db_session, "2025-12-30", "23.00", merchant="聚鑫福超市", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-聚鑫福超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is existing


def test_date_beyond_window_no_match(db_session):
    _txn(db_session, "2025-12-27", "23.00", merchant="聚鑫福超市", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-聚鑫福超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None  # 差 4 天


def test_different_merchant_no_match(db_session):
    _txn(db_session, "2025-12-31", "23.00", merchant="聚鑫福超市", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-美团外卖")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_empty_merchant_no_match(db_session):
    """空商户名不做形态 1 匹配（防止通用行/缺失行互相误配）"""
    _txn(db_session, "2025-12-31", "23.00", merchant="", source_type="ALIPAY")
    norm = _norm("2025-12-31", "23.00", merchant="")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_same_source_no_match(db_session):
    """跨源匹配只在不同来源之间生效"""
    _txn(db_session, "2025-12-31", "23.00", merchant="财付通-聚鑫福超市", source_type="BOC")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-聚鑫福超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


def test_ignored_txn_not_candidate(db_session):
    """IGNORED 交易不作为候选（用户已裁决忽略的记录不再干扰新导入）"""
    _txn(db_session, "2025-12-31", "23.00", merchant="聚鑫福超市", status="IGNORED")
    norm = _norm("2025-12-31", "23.00", merchant="财付通-聚鑫福超市")
    assert svc.find_cross_source_match(db_session, norm, "BOC") is None


# ---------- 形态 2：方向互反的转账对（还款/提现） ----------

def test_credit_card_repayment_pair(db_session):
    """信用卡还款：银行侧支出「平安信用卡中心还款业务」+ 信用卡侧收入「银联入账」"""
    existing = _txn(db_session, "2025-12-10", "1426.60",
                    merchant="平安信用卡中心还款业务(深圳)", source_type="BOC")
    norm = _norm("2025-12-10", "1426.60", direction="收入",
                 merchant="银联入账 刘赛 3452", description="银联入账 刘赛 3452")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is existing


def test_inverted_direction_without_hints_no_match(db_session):
    """方向互反但双侧无转账特征 → 不命中（避免无关收支被误配）"""
    _txn(db_session, "2025-12-10", "1426.60", merchant="某超市", source_type="BOC")
    norm = _norm("2025-12-10", "1426.60", direction="收入", merchant="工资", description="12月工资")
    assert svc.find_cross_source_match(db_session, norm, "CCB") is None


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
