"""pytest 全局护栏：测试数据库强制隔离。

规则：
1. 在任何 app.* 模块被导入（进而创建 engine）之前，把 DATABASE_URL 指向
   pytest 专用临时库；显式设置的 DATABASE_URL 环境变量会被尊重。
2. session 级守卫：解析后的数据库路径若指向生产 backend/beanweb.db
   （或历史事故遗留的仓库根 beanweb.db），测试立即失败——不依赖人为约定。
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
REPO_DIR = os.path.dirname(BACKEND_DIR)
PRODUCTION_DBS = {
    os.path.normpath(os.path.join(BACKEND_DIR, "beanweb.db")),
    os.path.normpath(os.path.join(REPO_DIR, "beanweb.db")),
}

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# pytest 专用隔离库（引擎惰性连接，现有测试全部使用各自的 :memory: 引擎；
# 该路径仅为未来 TestClient/get_db 类测试兜底）。用户显式设置时优先用户值。
_TEST_DB = os.path.join(os.environ.get("TEMP", "/tmp"), "beanweb_pytest.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)  # 清掉上次运行残留，避免陈旧 schema 干扰
    os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"


def resolved_db_path() -> str | None:
    """把 settings.DATABASE_URL 解析为绝对文件路径；非 sqlite 文件库返回 None。"""
    from app.core.config import settings
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path and path != ":memory:":
            return os.path.normpath(os.path.abspath(path))
    return None


@pytest.fixture(scope="session", autouse=True)
def guard_production_database():
    path = resolved_db_path()
    if path in PRODUCTION_DBS:
        pytest.fail(
            f"测试数据库指向生产库：{path}（tests/conftest.py 拒绝运行；"
            "请为测试设置隔离的 DATABASE_URL）"
        )
    yield
