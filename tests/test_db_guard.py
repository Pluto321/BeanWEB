"""数据库隔离守卫：显式断言测试环境绝不指向生产 beanweb.db。

conftest.py 的 session 级 fixture 会在收集后、任何测试执行前拦截错误配置；
本文件让该保证在测试报告中可见（双保险，而非依赖"人为保证"）。
"""
import os

from app.core.config import settings

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
REPO_DIR = os.path.dirname(BACKEND_DIR)
PRODUCTION_DBS = {
    os.path.normpath(os.path.join(BACKEND_DIR, "beanweb.db")),
    os.path.normpath(os.path.join(REPO_DIR, "beanweb.db")),
}


def _resolved_db_path() -> str | None:
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path and path != ":memory:":
            return os.path.normpath(os.path.abspath(path))
    return None


def test_test_database_never_points_to_production():
    path = _resolved_db_path()
    assert path not in PRODUCTION_DBS, f"测试 DATABASE_URL 指向生产数据库: {path}"


def test_conftest_redirects_default_database_url():
    """未显式设置 DATABASE_URL 时，conftest 必须已把默认值重定向到隔离库。"""
    url = settings.DATABASE_URL
    assert url.startswith("sqlite:///"), "测试环境 DATABASE_URL 必须是 sqlite URL"
    assert os.path.basename(url) != "beanweb.db", f"测试库文件名不得是生产库名: {url}"
