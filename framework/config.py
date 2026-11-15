"""环境配置中枢：所有可变参数集中在此，测试代码不再散落 os.getenv。

设计取舍：
- 12-factor 风格，环境变量是唯一配置来源，docker/CI/本地三种环境零改动切换；
- lru_cache 单例：一次进程内读取一次，测试代码 import 后直接用；
- 路径统一以仓库根为锚点（Path(__file__) 定位），不依赖 cwd，
  保证 pytest / CLI / Web 运行器三种入口行为一致。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# 仓库根 = framework/ 的上一级
REPO_ROOT = Path(__file__).resolve().parents[1]

# AI（LLM 网关）：未配置 API Key 时自动进入 offline 确定性模式，全流程仍可演示
AI_LLM_BASE_URL = "AI_LLM_BASE_URL"
AI_LLM_API_KEY = "AI_LLM_API_KEY"
AI_LLM_MODEL = "AI_LLM_MODEL"


@dataclass(frozen=True)
class Settings:
    """一次进程运行的全部配置快照。"""

    api_base_url: str = "http://127.0.0.1:8080"
    frontend_url: str = "http://127.0.0.1:5173"
    request_timeout: float = 10.0

    # 失败证据 / 报告落盘目录（CI 里 artifacts 从这里取）
    reports_dir: Path = REPO_ROOT / "reports"
    evidence_subdir: str = "evidence"
    triage_subdir: str = "triage"

    # LLM 网关
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    tags: tuple = field(default=())

    @property
    def evidence_dir(self) -> Path:
        return self.reports_dir / self.evidence_subdir

    @property
    def triage_dir(self) -> Path:
        return self.reports_dir / self.triage_subdir

    @property
    def llm_configured(self) -> bool:
        """是否配置了真实 LLM。未配置时 AI 模块走确定性 offline 模式。"""
        return bool(self.llm_api_key and self.llm_base_url)

    def as_env_dict(self) -> dict:
        """写进失败证据的执行环境快照（只放可诊断的非敏感字段）。"""
        import platform
        import socket

        return {
            "api_base_url": self.api_base_url,
            "frontend_url": self.frontend_url,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "host": socket.gethostname(),
            "llm_mode": "remote" if self.llm_configured else "offline",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        api_base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
        frontend_url=os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/"),
        request_timeout=float(os.getenv("API_TIMEOUT", "10")),
        reports_dir=Path(os.getenv("REPORTS_DIR", REPO_ROOT / "reports")),
        llm_base_url=os.getenv(AI_LLM_BASE_URL, "").rstrip("/"),
        llm_api_key=os.getenv(AI_LLM_API_KEY, ""),
        llm_model=os.getenv(AI_LLM_MODEL, "gpt-4o-mini"),
    )
