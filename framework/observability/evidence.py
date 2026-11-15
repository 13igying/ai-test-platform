"""统一失败证据采集（对应《改进方案》3.4）。

每次失败至少保留：
- 用例 ID、执行环境、开始/结束时间、失败阶段；
- API 请求与响应摘要（脱敏后）；
- 断言错误、异常堆栈、最后一次轮询状态；
- request_id（测试侧关联标识，用于与后台日志对齐）；
- UI 截图路径（仅在适用时）；
- 证据完整性标注（如：后端未透传 request_id → 标注 missing）。

该模块是 AI 失败分析（ai/failure_triage）的数据基础：
证据不完整时，AI 分析会明确说明"缺少什么"，而不是编造结论。

线程安全：pytest 默认单线程；xdist 下每个 worker 是独立进程，
全局单例 + 锁即可覆盖两种模式。
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from framework.config import get_settings
from framework.observability.redact import redact_obj, truncate


class EvidenceStore:
    """进程级单例：当前正在执行的用例的证据容器。

    使用方式：
    - pytest 插件在每条用例开始时调用 begin_test()；
    - BaseClient 每次 HTTP 交互 record_exchange()；
    - eventual.wait_for 轮询时 record_poll()；
    - 用例失败时插件 end_test() + dump() 落盘 reports/evidence/<case>.json。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._case: dict[str, Any] | None = None

    # ---------- 生命周期 ----------
    def begin_test(self, case_id: str, env: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._case = {
                "case_id": case_id,
                "env": env or {},
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "finished_at": None,
                "phase": None,          # 失败阶段：setup / call / teardown
                "assertion_error": None,  # 断言/异常文本（截断）
                "api_exchanges": [],    # 脱敏后的 HTTP 交互
                "poll_history": [],     # 最终一致性轮询记录
                "request_ids": [],      # 测试侧关联标识
                "screenshots": [],      # UI 截图 / Playwright Trace 路径
                "missing_evidence": [],  # 证据完整性标注
            }

    def end_test(self, phase: str, error_text: str | None = None) -> None:
        if self._case is None:
            return
        with self._lock:
            self._case["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            self._case["phase"] = phase
            if error_text:
                self._case["assertion_error"] = truncate(error_text)

    # ---------- 采集 ----------
    def record_exchange(self, exchange: dict[str, Any]) -> None:
        """记录一次 HTTP 交互（已在 client 层脱敏）。"""
        with self._lock:
            if self._case is None:
                return
            self._case["api_exchanges"].append(exchange)
            rid = exchange.get("request_id")
            if rid and rid not in self._case["request_ids"]:
                self._case["request_ids"].append(rid)

    def record_poll(self, poll: dict[str, Any]) -> None:
        """记录一次最终一致性轮询（desc/attempts/最后观测值）。"""
        with self._lock:
            if self._case is None:
                return
            self._case["poll_history"].append(redact_obj(poll))

    def record_screenshot(self, path: str | Path) -> None:
        with self._lock:
            if self._case is None:
                return
            self._case["screenshots"].append(str(path))

    def note_missing(self, what: str) -> None:
        """显式标注证据不完整——AI 分析据此声明"缺少什么"，而非编造。"""
        with self._lock:
            if self._case is None:
                return
            if what not in self._case["missing_evidence"]:
                self._case["missing_evidence"].append(what)

    # ---------- 输出 ----------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._case is None:
                return {"case_id": "(no active case)"}
            return json.loads(json.dumps(self._case, ensure_ascii=False, default=str))

    def dump(self, directory: Path | None = None) -> Path:
        """把当前证据写成 JSON 文件，返回文件路径。"""
        settings = get_settings()
        directory = directory or settings.evidence_dir
        directory.mkdir(parents=True, exist_ok=True)
        case = self.snapshot()
        safe = case.get("case_id", "unknown").replace("::", "__").replace("/", "_")
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in safe)
        path = directory / f"{safe}.json"
        path.write_text(
            json.dumps(case, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def reset(self) -> None:
        """测试间清理（主要供单测使用）。"""
        with self._lock:
            self._case = None


# 进程级单例：client / eventual / pytest_plugin 三方共享
store = EvidenceStore()
