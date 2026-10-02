"""微信账单 xlsx Importer 测试。

Fixture：tests/fixtures/wechat_sample.xlsx（generate_wechat_fixture.py 生成的合成数据）。
真实账单冒烟：账本/ 目录存在微信 xlsx 时自动运行，否则跳过。
所有 DB 测试用内存 SQLite，绝不触碰真实 beanweb.db。
"""
import asyncio
import glob
import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

import app.services.alipay_importer  # noqa: F401  注册 alipay/bank
import app.services.bank_importers  # noqa: F401  注册 boc/ccb
import app.services.wechat_importer  # noqa: F401  注册 wechat
from app.api.imports import analyze_import, commit_import
from app.models.models import Base, Transaction
from app.services.importer import ImporterRegistry

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
WECHAT_XLSX = os.path.join(FIXTURE_DIR, "wechat_sample.xlsx")
LEDGER_DIR = os.path.join(os.path.dirname(__file__), "..", "账本")


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _real_wechat():
    if not os.path.isdir(LEDGER_DIR):
        return []
    return glob.glob(os.path.join(LEDGER_DIR, "*.xlsx"))


# ---------- 注册表探测 ----------

def test_registry_detects_wechat_fixture():
    assert ImporterRegistry.get_importer(WECHAT_XLSX).name == "wechat"


def test_registry_no_regression():
    """CSV/PDF Importer 不受微信 xlsx 影响"""
    assert ImporterRegistry.get_importer(os.path.join(FIXTURE_DIR, "alipay_sample.csv")).name == "alipay"
    assert ImporterRegistry.get_importer(os.path.join(FIXTURE_DIR, "boc_sample.pdf")).name == "boc"


# ---------- parse / normalize ----------

def test_wechat_fixture_parse():
    imp = ImporterRegistry.get_importer(WECHAT_XLSX)
    rows = imp.parse(WECHAT_XLSX)
    assert len(rows) == 3
    # datetime 单元格 → 'YYYY-MM-DD HH:MM:SS' 字符串；数值单元格 → str；'/' 占位符 → 空
    assert rows[0]["交易时间"] == "2026-02-01 22:23:15"
    assert rows[0]["金额(元)"] == "9.82"
    assert rows[1]["金额(元)"] == "7"
    assert rows[0]["备注"] == ""
    assert rows[2]["支付方式"] == ""


def test_wechat_fixture_normalize():
    imp = ImporterRegistry.get_importer(WECHAT_XLSX)
    norms = [imp.normalize(r) for r in imp.parse(WECHAT_XLSX)]
    # 交易单号直接作为 source ID（全局唯一，无需合成）
    assert norms[0].source_transaction_id == "4200000000WTEST0001"
    assert norms[0].date == "2026-02-01" and norms[0].time == "22:23:15"
    assert norms[0].amount == Decimal("9.82") and norms[0].direction == "支出"
    assert norms[0].transaction_type == "商户消费"
    assert norms[0].merchant == "测试餐饮店" and norms[0].counterparty == "测试餐饮店"
    assert norms[0].payment_method == "测试银行信用卡(9042)"
    # 收入行：支付方式 '/' → 用「当前状态」兜底，可被零钱账户别名匹配
    assert norms[2].direction == "收入" and norms[2].amount == Decimal("2000")
    assert norms[2].payment_method == "已存入零钱"
    # 幂等：重新 parse + normalize 得到相同 source ID
    assert [imp.normalize(r).source_transaction_id for r in imp.parse(WECHAT_XLSX)] == \
        [n.source_transaction_id for n in norms]


# ---------- Analyze → Commit 集成 ----------

def test_wechat_analyze_commit_roundtrip(db_session, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "raw"))

    with open(WECHAT_XLSX, "rb") as f:
        up = UploadFile(f, filename="wechat_sample.xlsx")
        result = asyncio.run(analyze_import(up, db_session))
    assert result["parser"] == "wechat"
    assert result["stats"] == {"total": 3, "new": 3, "existing": 0, "possible_duplicate": 0, "invalid": 0}

    committed = commit_import(result["import_id"], db_session)
    assert committed["created"] == 3
    txns = db_session.query(Transaction).filter(Transaction.source_type == "WECHAT").all()
    assert len(txns) == 3
    assert {t.direction for t in txns} == {"支出", "收入"}

    # 同文件重复分析：文件级去重 + 交易单号 Layer1 全部 EXACT
    with open(WECHAT_XLSX, "rb") as f:
        up2 = UploadFile(f, filename="wechat_sample.xlsx")
        result2 = asyncio.run(analyze_import(up2, db_session))
    assert result2["stats"]["existing"] == 3 and result2["stats"]["new"] == 0


# ---------- 真实账单冒烟（账本/ 已 gitignore，仅本地存在时运行） ----------

@pytest.mark.skipif(not _real_wechat(), reason="账本/ 下没有微信 xlsx 账单（已 gitignore）")
def test_real_wechat_statement():
    files = _real_wechat()
    assert files, "应至少存在一个微信账单"
    imp = ImporterRegistry.get_importer(files[0])
    assert imp.name == "wechat"
    rows = imp.parse(files[0])
    assert rows
    norms = [imp.normalize(r) for r in rows]
    ids = [n.source_transaction_id for n in norms]
    assert len(ids) == len(set(ids)), "交易单号应唯一"
    for n in norms:
        assert n.amount > 0
        assert n.direction in ("支出", "收入", "不计收支")
        assert n.date and n.currency == "CNY"
