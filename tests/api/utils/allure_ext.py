"""兼容 shim：Allure 集成已迁移到 framework.observability.allure_ext。"""
from framework.observability.allure_ext import (  # noqa: F401
    HAS_ALLURE,
    allure,
    attach_json,
    attach_text,
)

__all__ = ["allure", "attach_json", "attach_text", "HAS_ALLURE"]
