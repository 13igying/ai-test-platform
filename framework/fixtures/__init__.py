"""可复用夹具实现（纯函数，不依赖 pytest；fixture 在 tests/*/conftest.py 包装）。"""
from framework.clients.base_client import SystemClient
from framework.config import get_settings
from framework.data_factory.user_factory import User, register_and_login


def make_anon_client(base_url: str | None = None) -> SystemClient:
    """未认证 client。"""
    return SystemClient(base_url or get_settings().api_base_url)


def make_user(base_url: str | None = None, prefix: str = "case") -> User:
    """每个用例独立的新注册用户（已登录）。"""
    return register_and_login(base_url or get_settings().api_base_url, prefix=prefix)


__all__ = ["make_anon_client", "make_user", "SystemClient", "User"]
