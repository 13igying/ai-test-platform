"""Page Object 包：前端各页面的元素定位与操作封装。

用例层从这里统一导入：
    from tests.e2e.pages import AccountPage, FeedPage, RegisterPage
"""
from tests.e2e.pages.account_page import AccountPage
from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.feed_page import FeedPage
from tests.e2e.pages.register_page import RegisterPage
from tests.e2e.pages.settings_page import SettingsPage

__all__ = ["BasePage", "RegisterPage", "AccountPage", "FeedPage", "SettingsPage"]

