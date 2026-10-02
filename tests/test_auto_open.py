"""LedgerManager.ensure_accounts_opened 测试：账户自动声明托管块。

契约：
- accounts.bean 不存在 → 创建含托管块的文件
- 缺失账户按字母序追加进托管块；已 open（手写或托管块内）跳过
- 手写行绝不修改（含日期）；托管块内仅本次 ensure 的账户允许把 open 日期改早
- 幂等：无变化不写文件
"""
import os
import time

import pytest

from app.services.ledger import LedgerManager

AUTO_BEGIN = LedgerManager.AUTO_OPEN_BEGIN
AUTO_END = LedgerManager.AUTO_OPEN_END


@pytest.fixture
def mgr(tmp_path):
    return LedgerManager(str(tmp_path))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_creates_accounts_bean_when_missing(mgr, tmp_path):
    mgr.ensure_accounts_opened(["Assets:BOC:6217"], "2025-12-01")
    content = _read(os.path.join(str(tmp_path), "accounts.bean"))
    assert "2025-12-01 open Assets:BOC:6217 CNY" in content
    assert AUTO_BEGIN in content and AUTO_END in content


def test_appends_sorted_and_idempotent(mgr, tmp_path):
    path = os.path.join(str(tmp_path), "accounts.bean")
    mgr.ensure_accounts_opened(["Assets:B"], "2025-12-01")
    mgr.ensure_accounts_opened(["Assets:A"], "2025-12-01")
    content = _read(path)
    assert content.index("open Assets:A") < content.index("open Assets:B")  # 字母序

    # 幂等：重复调用无变化不重写
    mtime_before = os.path.getmtime(path)
    time.sleep(0.02)
    mgr.ensure_accounts_opened(["Assets:B"], "2025-12-01")
    assert os.path.getmtime(path) == mtime_before


def test_handwritten_lines_untouched_and_opened_skipped(mgr, tmp_path):
    path = os.path.join(str(tmp_path), "accounts.bean")
    # 旧版形态：纯手写、无托管块
    with open(path, "w", encoding="utf-8") as f:
        f.write("2026-01-01 open Assets:BeanWEB CNY\n")
    mgr.ensure_accounts_opened(["Assets:BeanWEB", "Assets:New"], "2025-12-01")
    content = _read(path)
    # 手写行原样保留（已 open 的账户跳过，日期不被改早）
    assert "2026-01-01 open Assets:BeanWEB CNY" in content
    assert "2025-12-01 open Assets:New CNY" in content
    assert AUTO_BEGIN in content


def test_earlier_date_adjusts_only_requested_account(mgr, tmp_path):
    """回归：改早仅限本次 ensure 的账户，不得影响托管块内其它账户"""
    path = os.path.join(str(tmp_path), "accounts.bean")
    mgr.ensure_accounts_opened(["Assets:A", "Assets:B"], "2026-01-01")
    mgr.ensure_accounts_opened(["Assets:A"], "2025-01-01")  # 只有 A 请求更早日期
    content = _read(path)
    assert "2025-01-01 open Assets:A CNY" in content
    assert "2026-01-01 open Assets:B CNY" in content  # B 保持原 open 日期
