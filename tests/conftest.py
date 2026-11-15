"""顶层 conftest：全局 fixtures 与 Allure 环境信息。

环境变量（统一由 framework.config.Settings 读取）：
    API_BASE_URL  后端直连地址，默认 http://127.0.0.1:8080
    FRONTEND_URL  前端地址（E2E 用），默认 http://127.0.0.1:5173
"""
import os
import platform
import socket

import pytest

from framework.config import get_settings


def _write_allure_environment(config) -> None:
    """Allure 配套：带 --alluredir 运行时，把环境信息写进结果目录。

    报告首页 Overview -> Environment 卡片会展示这些键值对，
    汇报时一眼可查"这轮报告打的是哪个环境"。
    未装 allure-pytest 或未开 --alluredir 时静默跳过。
    """
    try:
        alluredir = config.getoption("--alluredir")
    except (ValueError, KeyError):
        return
    if not alluredir:
        return
    settings = get_settings()
    try:
        os.makedirs(alluredir, exist_ok=True)
        with open(
            os.path.join(str(alluredir), "environment.properties"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                "\n".join(
                    [
                        f"API_BASE_URL={settings.api_base_url}",
                        f"FRONTEND_URL={settings.frontend_url}",
                        f"Python={platform.python_version()}",
                        f"Platform={platform.platform()}",
                        f"Host={socket.gethostname()}",
                    ]
                )
                + "\n"
            )
    except OSError:
        pass  # 环境信息写不进去不影响测试本身


def pytest_configure(config):
    """pytest 钩子：初始化阶段写 Allure 环境信息。"""
    _write_allure_environment(config)


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return get_settings().api_base_url


@pytest.fixture(scope="session")
def frontend_url() -> str:
    return get_settings().frontend_url
