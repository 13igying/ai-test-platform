"""E2E（UI）测试夹具：Playwright 浏览器生命周期 + 失败自动截图。

设计说明（面试可讲）：
- 为什么自建 fixtures 而不依赖 pytest-playwright 插件？
  浏览器 session 级启动一次、每条用例独立 context（隔离 cookie/登录态）、
  失败自动全页截图并附到 Allure —— 这些定制自己做更可控；
- playwright 未安装 / Chromium 未下载时用例自动 skip 而非报错，
  保持套件"轻依赖可跑"（与 allure_ext 的优雅降级思路一致）。
"""
from __future__ import annotations

import pytest

from framework.observability.allure_ext import allure
from tests.e2e.config import DEFAULT_TIMEOUT_MS, E2E_SHOTS, VIEWPORT
from tests.gates import ensure_backend_ready, ensure_frontend_ready

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # 极简环境未装 playwright：UI 用例 skip，不影响 API 用例
    sync_playwright = None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """把每个执行阶段的结果挂到 item 上，teardown 阶段才能判断用例是否失败。"""
    rep = yield
    setattr(item, f"rep_{rep.when}", rep)
    return rep


@pytest.fixture(scope="session", autouse=True)
def stack_ready(api_base_url, frontend_url):
    """E2E 依赖整栈（前端页面 + 后端接口）：任一未就绪则快速失败。"""
    ensure_backend_ready(api_base_url, timeout=30.0)
    ensure_frontend_ready(frontend_url, timeout=30.0)


@pytest.fixture(scope="session")
def pw_runner():
    """Playwright 驱动进程（session 级，全量 UI 用例共用一次启动）。"""
    if sync_playwright is None:
        pytest.skip("未安装 playwright（pip install playwright），跳过 E2E UI 用例")
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(pw_runner):
    """Chromium 浏览器实例（session 级）。"""
    try:
        b = pw_runner.chromium.launch(headless=True)
    except Exception as e:  # 内核未下载等情况：给出修复指引而非裸报错
        pytest.skip(f"Chromium 启动失败（playwright install chromium 可修复）: {e}")
    yield b
    b.close()


@pytest.fixture
def page(request, browser, frontend_url):
    """每条用例独立浏览器上下文：互不污染 cookie / localStorage / 登录态。"""
    context = browser.new_context(viewport=VIEWPORT, base_url=frontend_url)
    pg = context.new_page()
    pg.set_default_timeout(DEFAULT_TIMEOUT_MS)
    yield pg
    # 失败自动截图：全页截图落盘 + 作为 PNG 附件进 Allure 报告
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        safe = request.node.nodeid.replace("::", "__").replace("/", "_")
        E2E_SHOTS.mkdir(parents=True, exist_ok=True)
        path = E2E_SHOTS / f"{safe}.png"
        try:
            pg.screenshot(path=str(path), full_page=True)
            allure.attach(
                path.read_bytes(),
                name=f"失败截图 {request.node.name}",
                attachment_type=allure.attachment_type.PNG,
            )
        except Exception:
            pass  # 页面可能已崩溃，截图失败不影响用例结果本身
    context.close()
