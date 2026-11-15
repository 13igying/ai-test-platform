"""失败分诊阶段 2：规则分类器（确定性、可解释、零成本、可单测）。

分类规则按优先级排列，命中即停（每条规则给出结论 + 置信度 + 信号）：
1. environment   —— 连接不上/超时：不是代码问题，先修环境；
2. data_issue    —— 限流 429 / 冲突 409 / 重复数据：测试数据治理问题；
3. test_script_issue —— KeyError/契约/schema 类：测试代码自身坏了；
4. needs_analysis    —— WaitTimeoutError：轮询超时带完整现场，"大概率是缺陷
   但不能武断"，交给下一阶段深度分析（规则不该替人下结论）；
5. code_defect   —— 5xx / 死锁特征 / 业务断言失败：疑似产品缺陷，进入缺陷候选。

为什么规则先行而不是直接 LLM：规则便宜、稳定、可解释；LLM 只处理
规则无法定论的"灰色地带"——这是成本与质量的最优分层。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ai.failure_triage.collector import FailureRecord, extract_signals

# 分类结论常量（与改进方案 5.4 的四分类 + 待分析对齐）
C_ENV = "environment_issue"
C_DATA = "test_data_issue"
C_SCRIPT = "test_script_issue"
C_DEFECT = "suspected_code_defect"
C_ANALYZE = "needs_deep_analysis"

_TRANSIENT_ENV_PAT = re.compile(
    r"ConnectError|ConnectTimeout|ReadTimeout|Connection refused|"
    r"后端.*未就绪|All connection attempts failed",
    re.IGNORECASE,
)
_DATA_PAT = re.compile(r"429|限流|rate limit|409|duplicate|already exists|已存在", re.IGNORECASE)
_SCRIPT_PAT = re.compile(
    r"KeyError|AttributeError|TypeError|JSONDecodeError|契约|未注册的 schema|schema"
)
_DEFECT_PAT = re.compile(r"deadlock|Deadlock|死锁|Error 1213|Error 1205", re.IGNORECASE)


@dataclass
class Classification:
    category: str
    confidence: float
    rule: str                 # 命中的规则名（可解释性）
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "rule": self.rule,
            "signals": self.signals,
        }


def classify(record: FailureRecord, signals: dict[str, Any] | None = None) -> Classification:
    """规则分类：按优先级命中即停。signals 可预提取（测试时可注入）。"""
    sig = signals if signals is not None else extract_signals(record)
    text = f"{record.message}"
    etype = sig.get("exception_type") or ""
    status = sig.get("last_status")

    # 1. 环境问题：连不上 / 网络层超时（status=0 表示请求根本没到后端）
    if sig.get("last_status") == 0 or _TRANSIENT_ENV_PAT.search(text):
        return Classification(C_ENV, 0.95, "network_or_backend_down", sig)

    # 2. 数据问题：限流 / 冲突 / 重复
    if status in (409, 429) or _DATA_PAT.search(text):
        return Classification(C_DATA, 0.85, "rate_limit_or_data_conflict", sig)

    # 3. 测试脚本问题：KeyError/契约校验/schema 未注册——测试代码自己坏了
    if etype in ("KeyError", "AttributeError", "TypeError", "JSONDecodeError") or _SCRIPT_PAT.search(
        text
    ):
        return Classification(C_SCRIPT, 0.8, "test_code_or_contract_error", sig)

    # 4. 轮询超时：现场完整但结论不能武断 → 深度分析
    if etype == "WaitTimeoutError" or "等待超时" in text:
        return Classification(C_ANALYZE, 0.5, "wait_timeout_with_context", sig)

    # 5. 疑似缺陷：5xx / 死锁特征 / 其余业务断言失败
    if (isinstance(status, int) and status >= 500) or _DEFECT_PAT.search(text):
        return Classification(C_DEFECT, 0.9, "server_error_or_deadlock", sig)
    if etype in ("AssertionError", "APIError") or record.outcome == "failed":
        return Classification(C_DEFECT, 0.6, "business_assertion_failed", sig)

    # 兜底：规则覆盖不到的（如 error 无类型信息）
    return Classification(C_ANALYZE, 0.3, "unclassified_error", sig)
