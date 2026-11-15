"""页面对象基类（PO 模式）。

为什么用 PO 模式（面试可讲）：
- 元素定位只出现在 Page 类里，用例层只写业务动作和断言；
- 前端改版（改类名/结构）只需改对应 Page 一个文件，用例零改动；
- 定位策略统一约定：优先语义化属性（get_by_role / autocomplete），
  弱化易变的样式类名。

本基类封装三类通用能力：导航（open/nav）、状态（url/title）、证据（screenshot）。
"""
from __future__ import annotations

from pathlib import Path

# 默认截图目录：tests/ui_shots（Web 测试运行器从该目录读取截图墙）
SHOTS_DIR = Path(__file__).resolve().parents[2] / "ui_shots"


class BasePage:
    """所有页面对象的基类，子类通过覆盖 PATH 声明自己的路由。"""

    PATH = "/"

    def __init__(self, page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    # ---------- 导航 ----------
    def open(self, wait: str = "load") -> "BasePage":
        """打开本页（base_url + PATH），返回自身以便链式调用。

        为什么默认等 load 而不是 networkidle？
        Feed 页有持续轮询请求，公网延迟下 networkidle 可能永远达不到，
        等待必然超时；load 事件 + 用例内显式 settle 等待更稳定。
        """
        self.page.goto(f"{self.base_url}{self.PATH}", wait_until=wait)
        return self

    def nav(self, name: str, wait_ms: int = 1200) -> None:
        """点击侧边栏导航链接（推荐/热榜/账号/设置）。"""
        self.page.get_by_role("link", name=name).click()
        if wait_ms:
            self.page.wait_for_timeout(wait_ms)

    # ---------- 状态 ----------
    @property
    def url(self) -> str:
        return self.page.url

    @property
    def title(self) -> str:
        return self.page.title()

    # ---------- 证据 ----------
    def screenshot(
        self,
        name: str,
        directory: Path | None = None,
        full_page: bool = False,
    ) -> str:
        """截图到指定目录（默认 ui_shots），返回文件名。"""
        directory = Path(directory) if directory else SHOTS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=full_page)
        return path.name
