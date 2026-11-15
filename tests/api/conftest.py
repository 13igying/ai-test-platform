"""API 测试层 conftest：后端就绪门禁 + client 与用户 fixtures。"""
from __future__ import annotations

import pytest

from framework.clients import SystemClient
from framework.data_factory import User, register_and_login
from tests.gates import ensure_backend_ready


@pytest.fixture(scope="session", autouse=True)
def backend_ready(api_base_url):
    """session 级：确保后端可用，否则快速失败（仅作用于需要后端的目录）。"""
    ensure_backend_ready(api_base_url, timeout=30.0)


@pytest.fixture
def anon_client(api_base_url) -> SystemClient:
    """未认证 client（用例级，自动关闭）。"""
    c = SystemClient(api_base_url)
    yield c
    c.close()


@pytest.fixture
def user(api_base_url) -> User:
    """每个用例独立的新注册用户（已登录）。"""
    return register_and_login(api_base_url, prefix="case")


@pytest.fixture(scope="module")
def module_user(api_base_url) -> User:
    """模块级共享用户（减少注册次数，规避限流）。"""
    return register_and_login(api_base_url, prefix="mod")