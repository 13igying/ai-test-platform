"""注册页页面对象。"""
from tests.e2e.pages.base_page import BasePage


class RegisterPage(BasePage):
    """``/account/register`` —— 注册表单。

    定位说明：页面侧边栏还有搜索框等 input，必须用 autocomplete 属性
    精确定位（username / new-password），避免 fill 打进错误输入框。
    """

    PATH = "/account/register"

    def fill_form(self, username: str, password: str) -> "RegisterPage":
        """填写注册表单（不提交）。"""
        self.page.locator("input[autocomplete='username']").fill(username)
        self.page.locator("input[autocomplete='new-password']").fill(password)
        return self

    def submit(self, wait_ms: int = 1500) -> None:
        """点击注册按钮。

        页面可能有多个含"注册"文案的元素，限定表单主按钮 ``button.primary``。
        """
        self.page.locator("button.primary", has_text="注册").click()
        if wait_ms:
            self.page.wait_for_timeout(wait_ms)

    def register(self, username: str, password: str, wait_ms: int = 1500) -> None:
        """填写并提交注册表单。"""
        self.fill_form(username, password)
        self.submit(wait_ms)

    def is_success(self) -> bool:
        """注册成功后前端会跳离注册页；仍停留在注册页即视为失败。"""
        return self.PATH not in self.page.url
