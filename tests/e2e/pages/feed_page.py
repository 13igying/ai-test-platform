"""Feed 流页面对象：推荐页与热榜页。"""
from tests.e2e.pages.base_page import BasePage


class FeedPage(BasePage):
    """``/``（推荐）与 ``/hot``（热榜）—— 两个 Tab 共用一个页面组件。"""

    PATH = "/"

    # ---------- 动作 ----------
    def switch_hot(self, wait_ms: int = 1200) -> None:
        """点击侧边栏"热榜"切换到热榜页。"""
        self.nav("热榜", wait_ms)

    # ---------- 状态断言 ----------
    def is_recommend(self) -> bool:
        """当前是否停留在推荐页（base_url 本身）。"""
        return self.page.url.rstrip("/") == self.base_url

    def is_hot(self) -> bool:
        """当前是否在热榜页。"""
        return "/hot" in self.page.url
