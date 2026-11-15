"""安全测试层 conftest：后端门禁 + 基础 fixtures（越权矩阵用独立用户）。"""
from __future__ import annotations

import pytest

from framework.clients import SystemClient
from framework.data_factory import User, register_and_login
from tests.gates import ensure_backend_ready


@pytest.fixture(scope="session", autouse=True)
def backend_ready(api_base_url):
    ensure_backend_ready(api_base_url, timeout=30.0)


@pytest.fixture
def anon_client(api_base_url) -> SystemClient:
    c = SystemClient(api_base_url)
    yield c
    c.close()


@pytest.fixture
def user(api_base_url) -> User:
    return register_and_login(api_base_url, prefix="sec")


@pytest.fixture(scope="module")
def module_user(api_base_url) -> User:
    return register_and_login(api_base_url, prefix="secm")
