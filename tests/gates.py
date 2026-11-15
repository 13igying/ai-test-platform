"""就绪门禁：需要真实环境的测试目录（api/e2e/integration/security）显式启用。

为什么从顶层 autouse 降级为按需：
- tests/unit/（框架与 AI 模块的离线单测）不依赖任何后端，
  顶层 autouse 门禁会让"离线单测"在无后端环境直接退出；
- 门禁放在各子目录 conftest 中 autouse，天然只作用于需要后端的用例。
"""
from __future__ import annotations

import time

import httpx
import pytest


def _probe(url: str, timeout: float = 30.0) -> None:
    """轮询探活直到服务就绪（monotonic 计时，与 wait_for 口径一致）。"""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=3.0)
            if r.status_code == 200:
                return
            last_err = RuntimeError(f"HTTP {r.status_code}")
        except httpx.HTTPError as e:
            last_err = e
        time.sleep(0.5)
    pytest.exit(f"服务 {url} 未就绪: {last_err}", returncode=4)


def ensure_backend_ready(base_url: str, timeout: float = 30.0) -> None:
    """后端 /healthz 探活；未就绪时快速失败（fail fast）。"""
    _probe(f"{base_url.rstrip('/')}/healthz", timeout=timeout)


def ensure_frontend_ready(frontend_url: str, timeout: float = 30.0) -> None:
    """前端首页探活（E2E 用）。"""
    _probe(frontend_url.rstrip("/"), timeout=timeout)
