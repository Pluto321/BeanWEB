"""GET /api/transactions 分页双契约测试 + /counts 计数端点。

- 不带 page/page_size：旧契约，返回全量裸数组（Dashboard/ExportPage 依赖）
- 带 page/page_size：新契约 {items, total, page, page_size, status_counts, grand_total}
  排序 date DESC, id DESC；status/search/date 过滤服务端执行

直调说明：函数默认值是 FastAPI 的 Query 对象（装饰器路径由框架解析），
测试直调时必须显式传全部可选参数为 None。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import get_transaction_counts, get_transactions
from app.models.models import Base, Transaction


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed(db, n=60):
    for i in range(1, n + 1):
        db.add(Transaction(
            date=f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}",
            amount=str(i), merchant=f"商户{i}",
            description=f"描述{i}" if i % 2 == 0 else "",
            counterparty=f"对方{i}" if i % 3 == 0 else "",
            status=["REVIEW_REQUIRED", "CONFIRMED", "POSSIBLE_DUPLICATE", "IGNORED"][i % 4],
        ))
    db.commit()


def _call(db, **kw):
    params = dict(status=None, page=None, page_size=None, search=None, date_from=None, date_to=None, db=db)
    params.update(kw)
    return get_transactions(**params)


def test_legacy_no_params_returns_bare_array(db_session):
    """旧契约：无分页参数 → 全量裸数组（兼容 Dashboard/ExportPage）"""
    _seed(db_session, 10)
    result = _call(db_session)
    assert isinstance(result, list) and len(result) == 10
    assert [t.id for t in result][:3] == [1, 2, 3]  # id 升序稳定排序


def test_paginated_shape_and_order(db_session):
    _seed(db_session, 60)
    result = _call(db_session, page=1, page_size=50)
    assert result["total"] == 60
    assert result["page"] == 1 and result["page_size"] == 50
    assert len(result["items"]) == 50
    # 排序：date DESC, id DESC（审核工作台：最新优先）
    dates = [t.date for t in result["items"]]
    assert dates == sorted(dates, reverse=True)
    # status_counts 全局口径（不受筛选影响）
    assert result["status_counts"] == {
        "REVIEW_REQUIRED": 15, "CONFIRMED": 15, "POSSIBLE_DUPLICATE": 15, "IGNORED": 15,
    }
    assert result["grand_total"] == 60


def test_paginated_page2_and_status_filter(db_session):
    _seed(db_session, 60)
    page2 = _call(db_session, page=2, page_size=50)
    assert len(page2["items"]) == 10 and page2["page"] == 2

    filtered = _call(db_session, status="CONFIRMED", page=1, page_size=50)
    assert filtered["total"] == 15
    assert all(t.status == "CONFIRMED" for t in filtered["items"])
    # 全局 chips 计数不受 status 筛选影响
    assert filtered["grand_total"] == 60


def test_search_and_date_filters(db_session):
    _seed(db_session, 60)
    r = _call(db_session, search="商户3", page=1, page_size=50)
    assert 0 < r["total"] <= 11  # 商户3、商户30-39……LIKE 子串
    assert all("商户3" in (t.merchant or "") for t in r["items"])

    r3 = _call(db_session, date_from="2026-12-01", date_to="2026-12-31", page=1, page_size=50)
    assert r3["total"] > 0
    assert all("2026-12-" in t.date for t in r3["items"])


def test_counts_endpoint(db_session):
    _seed(db_session, 10)
    # status = [RR, CC, PD, IG][i % 4]，i=1..10 → CC{1,5,9} PD{2,6,10} IG{3,7} RR{4,8}
    counts = get_transaction_counts(db=db_session)
    assert counts == {"REVIEW_REQUIRED": 2, "CONFIRMED": 3, "POSSIBLE_DUPLICATE": 3, "IGNORED": 2}
