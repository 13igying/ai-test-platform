#!/usr/bin/env python3
"""
UI 自动化演示（Web 运行器入口）：Playwright 驱动真实浏览器，模拟用户完整操作流程。

本文件是 tests/e2e PO 框架的"可执行演示版"：
- 页面元素与操作全部复用 tests/e2e/pages/（与 pytest E2E 用例共用同一套页面对象，
  元素定位只维护一份，前端改版只需改 pages/）；
- 对外契约保持不变 —— test_runner_server.py 以子进程方式调用本文件，
  解析步骤日志（✅/❌/📸），并读取 ui_shots/ 平铺截图与 result.json 摘要。

流程：打开首页 → 注册新用户 → 登录 → 浏览推荐页 → 切换热榜 →
      进入账号页 → 查看设置页 → 全程每步截图。

由 test_runner_server.py 以子进程方式调用，输出步骤日志 + 截图路径。

环境变量 FRONTEND_URL 指向前端地址，例：
    FRONTEND_URL=http://45.207.222.231:5173 python ui_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

# 允许以 `python tests/ui_demo.py` 方式从任意 cwd 启动（test_runner_server 以仓库根为 cwd）
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("未安装 playwright：pip install playwright && playwright install chromium",
          file=sys.stderr)
    sys.exit(2)

from tests.e2e.config import DEFAULT_TIMEOUT_MS, VIEWPORT  # noqa: E402
from tests.e2e.pages import AccountPage, FeedPage, RegisterPage  # noqa: E402

FRONTEND = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
SHOTS = Path(__file__).parent / "ui_shots"
SHOTS.mkdir(parents=True, exist_ok=True)
PASSWORD = "Passw0rd!123"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def shot(page, name: str) -> str:
    p = SHOTS / f"{name}.png"
    page.screenshot(path=str(p), full_page=False)
    log(f"📸 截图: {name}.png")
    return p.name


def main() -> int:
    user = f"uidemo_{uuid.uuid4().hex[:8]}"
    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"name": name, "ok": ok, "detail": detail})
        log(f"{'✅' if ok else '❌'} {name} {detail}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)

        # 1. 打开首页
        log("🌐 打开前端首页…")
        home = FeedPage(page, FRONTEND).open()
        step("打开首页", home.title != "", f"title={home.title!r}")
        shot(page, "01_home")

        # 2. 进入注册页
        reg = RegisterPage(page, FRONTEND).open()
        step("进入注册页", RegisterPage.PATH in page.url)
        shot(page, "02_register_page")

        # 3. 填写注册表单并提交
        #    （注意：侧边栏有搜索框，页面对象内部用 autocomplete 精确定位）
        reg.fill_form(user, PASSWORD)
        shot(page, "03_register_filled")
        reg.submit()
        step("提交注册", reg.is_success(), f"user={user}")
        shot(page, "04_register_done")

        # 4. 登录（若注册后未自动登录）
        acct = AccountPage(page, FRONTEND).open()
        if acct.has_login_form():
            acct.fill_login(user, PASSWORD)
            shot(page, "05_login_filled")
            # 页面有两个"登录"按钮（侧边栏 + 表单），页面对象内部用 primary 精确匹配
            acct.submit_login()
        page.wait_for_timeout(500)
        step("登录", acct.is_logged_in(user), f"user={user}")
        shot(page, "06_after_login")

        # 5. 浏览推荐页
        feed = FeedPage(page, FRONTEND).open()
        page.wait_for_timeout(1000)
        step("浏览推荐页", True, feed.url)
        shot(page, "07_feed")

        # 6. 切换热榜
        feed.switch_hot()
        step("切换热榜", feed.is_hot())
        shot(page, "08_hot")

        # 7. 账号页
        acct.nav("账号")
        step("进入账号页", "/account" in acct.url)
        shot(page, "09_account")

        # 8. 设置页
        acct.nav("设置")
        step("进入设置页", "/settings" in page.url)
        shot(page, "10_settings")

        browser.close()

    result = {
        "user": user,
        "steps": steps,
        "passed": all(s["ok"] for s in steps),
        "shots": sorted(p.name for p in SHOTS.glob("*.png")),
    }
    (SHOTS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    log(f"{'🎉 全部步骤通过' if result['passed'] else '⚠️ 有步骤失败'}，共 {len(steps)} 步")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
