"""账号页页面对象：未登录时是登录表单，登录后是个人主页。"""
from tests.e2e.pages.base_page import BasePage


class AccountPage(BasePage):
    """``/account`` —— 登录 / 个人主页（同一路由按登录态渲染）。"""

    PATH = "/account"

    # ---------- 登录 ----------
    def has_login_form(self) -> bool:
        """页面是否处于未登录态（显示登录卡片）。"""
        return self.page.locator("input[autocomplete='username']").count() > 0

    def fill_login(self, username: str, password: str) -> "AccountPage":
        """填写登录表单（autocomplete: username / current-password）。"""
        self.page.locator("input[autocomplete='username']").fill(username)
        self.page.locator("input[autocomplete='current-password']").fill(password)
        return self

    def submit_login(self, wait_ms: int = 1500) -> None:
        """点击登录按钮。

        页面有两个"登录"按钮（侧边栏 + 表单），限定表单内 primary 按钮精确匹配。
        """
        self.page.locator("button.primary", has_text="登录").click()
        if wait_ms:
            self.page.wait_for_timeout(wait_ms)

    def login(self, username: str, password: str, wait_ms: int = 1500) -> None:
        """填写并提交登录表单。"""
        self.fill_login(username, password)
        self.submit_login(wait_ms)

    def login_if_needed(self, username: str, password: str) -> "AccountPage":
        """注册后前端可能已自动登录：仅当出现登录表单时才登录。"""
        if self.has_login_form():
            self.login(username, password)
        return self

    # ---------- 登录态断言 ----------
    def is_logged_in(self, username: str) -> bool:
        """登录成功的判据：登录卡片消失 + 个人主页出现 @用户名。"""
        return (
            self.page.locator(".login-card").count() == 0
            and self.page.locator(f"text=@{username}").count() > 0
        )
