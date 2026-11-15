"""pytest 插件：自动采集每条失败用例的证据（零用例侵入）。

注册方式（tests/conftest.py）：
    pytest_plugins = ("framework.observability.pytest_plugin",)

工作流：
1. pytest_runtest_logstart —— 用例开始，初始化证据容器；
2. BaseClient / wait_for 在执行过程中持续填充 HTTP 交互与轮询记录；
3. pytest_runtest_makereport —— call/teardown 失败时：
   证据落盘 reports/evidence/<case>.json + 挂 Allure 附件。

设计取舍：
- 只在失败时落盘：通过用例的证据量可控，报告目录干净；
- setup 阶段失败（fixture 异常）同样采集——环境/数据问题正是
  AI 分类要区分的重要类别，不能因为"还没进用例体"就丢证据。
"""
from __future__ import annotations

import pytest

from framework.config import get_settings
from framework.observability.allure_ext import attach_json
from framework.observability.evidence import store


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """新式 hook wrapper（pytest>=8）：拿到报告后挂到 item 并在失败时采集证据。"""
    rep = yield
    setattr(item, f"rep_{rep.when}", rep)

    failed = rep.failed
    if not failed:
        return rep

    # 失败：结束证据采集并落盘（call / setup / teardown 任一阶段）
    store.end_test(phase=rep.when, error_text=str(rep.longrepr))
    try:
        path = store.dump()
        attach_json(
            f"[失败证据] {item.nodeid}（{rep.when}）",
            {"evidence_file": str(path), "evidence": store.snapshot()},
        )
    except Exception:  # 证据落盘失败绝不影响用例结果本身
        pass
    return rep


@pytest.fixture(autouse=True)
def _evidence_lifecycle(request):
    """每条用例开始时初始化证据容器；结束（无论成败）重置，防止串扰。"""
    settings = get_settings()
    store.begin_test(request.node.nodeid, env=settings.as_env_dict())
    yield
    store.reset()
