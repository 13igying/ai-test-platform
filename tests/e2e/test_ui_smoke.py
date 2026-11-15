"""E2E UI 冒烟：Playwright + Page Object 分层（与 ui_demo.py 走同一用户旅程）。

用例结构与 API 套件同款风格：
- Allure 第二步：feature/story/severity 装饰器；
- 第三步：失败自动截图作为附件（见 tests/e2e/conftest.py 的 page 夹具）；
- module 级 logged_page 夹具复用登录态，减少注册次数（前端代理路径有限流）。

运行（远程环境示例，PowerShell）：
    $env:API_BASE_URL  = "http://45.207.222.231:8080"
    $env:FRONTEND_URL  = "http://45.207.222.231:5173"
    pytest tests/e2e -v
"""
import pytest

from tests.api.utils.allure_ext import allure
from tests.api.utils.client import unique_password, unique_username
from tests.e2e.config import DEFAULT_TIMEOUT_MS, E2E_SHOTS, UI_PASSWORD, VIEWPORT
from tests.e2e.pages import AccountPage, FeedPage, RegisterPage, SettingsPage

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


@pytest.fixture(scope="module")
def logged_page(browser, frontend_url):
    """module 级共享登录态：注册一个用户并登录一次，本模块用例复用。"""
    context = browser.new_context(viewport=VIEWPORT, base_url=frontend_url)
    page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)
    user = unique_username("ui")
    pwd = unique_password()
    RegisterPage(page, frontend_url).open().register(user, pwd)
    AccountPage(page, frontend_url).open().login_if_needed(user, pwd)
    yield page, user
    context.close()


@allure.feature("前端 UI 自动化")
@allure.story("用户注册")
class TestRegister:
    @allure.severity("blocker")
    def test_register_success_redirects(self, page, frontend_url):
        """注册成功后前端应跳离注册页。"""
        reg = RegisterPage(page, frontend_url).open()
        user = unique_username("ui")
        reg.fill_form(user, UI_PASSWORD)
        reg.screenshot("e2e_register_filled", directory=E2E_SHOTS)
        reg.submit()
        assert reg.is_success(), f"注册后仍停留在注册页: {reg.url}"
        reg.screenshot("e2e_register_done", directory=E2E_SHOTS)


@allure.feature("前端 UI 自动化")
@allure.story("用户登录")
class TestLogin:
    @allure.severity("blocker")
    def test_login_shows_profile(self, logged_page, frontend_url):
        """登录成功：登录卡片消失，个人主页出现 @用户名。"""
        page, user = logged_page
        acct = AccountPage(page, frontend_url)
        assert acct.is_logged_in(user), f"登录态未生效: {acct.url}"


@allure.feature("前端 UI 自动化")
@allure.story("Feed 浏览")
class TestFeed:
    @allure.severity("critical")
    def test_recommend_feed_visible(self, logged_page, frontend_url):
        """首页推荐流可打开：停留在根路径且页面完成渲染（title 非空）。"""
        page, _ = logged_page
        feed = FeedPage(page, frontend_url).open()
        page.wait_for_timeout(1000)
        assert feed.is_recommend(), f"未停留在推荐页: {feed.url}"
        assert feed.title != "", "首页标题为空，页面可能未渲染"

    @allure.severity("normal")
    def test_switch_to_hot(self, logged_page, frontend_url):
        """侧边栏可切换到热榜页。"""
        page, _ = logged_page
        feed = FeedPage(page, frontend_url).open()
        feed.switch_hot()
        assert feed.is_hot(), f"切换热榜后 URL 异常: {feed.url}"


@allure.feature("前端 UI 自动化")
@allure.story("页面导航")
class TestNavigation:
    @allure.severity("normal")
    def test_account_page_keeps_logged_in(self, logged_page, frontend_url):
        """侧边栏可进入账号页，且登录态保持。"""
        page, user = logged_page
        acct = AccountPage(page, frontend_url)
        acct.nav("账号")
        assert "/account" in acct.url, f"账号页 URL 异常: {acct.url}"
        assert acct.is_logged_in(user), "账号页应保持登录态"

    @allure.severity("normal")
    def test_settings_page(self, logged_page, frontend_url):
        """侧边栏可进入设置页。"""
        page, _ = logged_page
        settings = SettingsPage(page, frontend_url)
        settings.nav("设置")
        assert "/settings" in settings.url, f"设置页 URL 异常: {settings.url}"
