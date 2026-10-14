"""路由 × 静态服务冒烟：锁住 Mount 与 API 匹配顺序的回归。

背景（2026-10-14 bug 报告）：3e56b72 曾用 Mount("/") 挂前端 dist，吞掉了依赖
redirect_slashes 307 的无斜杠 API 变体（/api/transactions → 404）。存量测试为
直调模式（不经 URL），路由形状回归只能由本文件兜底；dist 未 build 时自动跳过。
"""
import os

import pytest
from starlette.testclient import TestClient

from app.db.session import engine
from app.models.models import Base


@pytest.fixture(scope="module", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(scope="module")
def client():
    from app.core.config import settings
    if not os.path.isdir(settings.FRONTEND_DIST_DIR):
        pytest.skip("frontend/dist 不存在（未 build），跳过静态服务冒烟")
    from main import app
    return TestClient(app)


def test_slashless_api_routes_not_swallowed(client):
    """无斜杠 /api/transactions、/api/imports 必须命中路由（307 到带斜杠 canonical），
    绝不能被静态服务吞成 404。"""
    r = client.get("/api/transactions?page=1&page_size=5", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].endswith("/api/transactions/?page=1&page_size=5")
    assert client.get("/api/imports", follow_redirects=False).status_code == 307


def test_api_404_stays_json_not_spa(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_index_and_spa_fallback(client):
    assert 'id="root"' in client.get("/").text
    assert 'id="root"' in client.get("/transactions").text
