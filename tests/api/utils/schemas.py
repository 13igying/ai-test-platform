"""兼容 shim：响应契约已迁移到 framework.assertions.schema（jsonschema 实现）。"""
from framework.assertions.schema import SCHEMAS, validate_schema  # noqa: F401

__all__ = ["SCHEMAS", "validate_schema"]
