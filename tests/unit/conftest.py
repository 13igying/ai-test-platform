"""单元测试层 conftest:不依赖后端(离线),不注册任何环境门禁。

覆盖对象:framework/*(eventual、redact、evidence、base_client)与
ai/*(case_generation、failure_triage)。这层是 CI 里的"offline 单测 job",
保证框架与 AI 平台逻辑在无后端环境即可验证。
"""
from __future__ import annotations

import pytest

from framework.config import get_settings


@pytest.fixture(autouse=True)
def _force_offline_llm(monkeypatch):
    """unit 层契约(见 tests/gates.py):AI 模块一律 offline。

    本机可能为真实演示配置了 AI_LLM_* 环境变量(remote 模式),
    单测必须与之解耦:清掉相关变量并重建 Settings 单例,
    防止单测意外打真实 LLM(慢/不稳定/费用)。
    """
    for var in ("AI_LLM_BASE_URL", "AI_LLM_API_KEY", "AI_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

