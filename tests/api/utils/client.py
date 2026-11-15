"""兼容 shim：client 实现已迁移到 framework.clients（旧导入路径过渡期保留）。

新代码一律 `from framework.clients import SystemClient`；
本文件保证存量用例 / Web 运行器（test_runner_server.py）零改动。
"""
from framework.clients.base_client import (  # noqa: F401
    APIError,
    APIClient,
    BaseClient,
    SystemClient,
)
from framework.data_factory.user_factory import (  # noqa: F401
    unique_password,
    unique_username,
)

__all__ = [
    "APIError",
    "APIClient",
    "BaseClient",
    "SystemClient",
    "unique_username",
    "unique_password",
]
