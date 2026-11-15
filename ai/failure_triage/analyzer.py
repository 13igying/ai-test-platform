"""失败分诊阶段 3：深度分析器（规则结论 + 可选 LLM 归因，离线可完整降级）。

输出契约 TriageResult（Pydantic，JSON 报告直接由它保证）：
- 疑似模块 / 关键证据 / 假设列表 / 缺失信息 / 建议动作 / 是否缺陷候选；
- conclusion 固定为 hypothesis_needs_human_confirmation：分诊只"到假设为止"，
  会不会是产品缺陷必须人工确认——AI 不替人签发缺陷单；
- LLM 模式：把【规则结论 + 脱敏证据】喂给模型要归因假设；offline 或
  网关异常时 analysis_source=rules_only（行为可预测，CI 可依赖）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai.case_generation.gateway import GatewayError, LLMGateway, OfflineModeError
from ai.failure_triage.classifier import Classification
from framework.observability.redact import deep_redact

TRIAGE_SYSTEM_PROMPT = """\
你是资深后端测试专家，对一条失败的 API 自动化测试做根因分诊。
输入包含：失败记录、规则分类器的初步结论、脱敏后的执行证据（HTTP 交互/轮询历史）。
要求：
1. 最多给出 3 条假设，按可能性排序；每条假设给出 cause（一句中文归因）、
   basis（引用证据中的具体字段/值）、confidence(0~1)；
2. 证据不足以支撑的结论必须写进 missing_info，禁止编造；
3. recommended_actions 给出 2~4 条可执行动作（查什么日志、跑什么复现）；
4. 只输出 JSON，格式：
{"suspected_module": "...", "hypotheses": [{"cause": "...", "basis": "...", "confidence": 0.0}],
 "missing_info": ["..."], "recommended_actions": ["..."], "defect_candidate": false}
"""


class Hypothesis(BaseModel):
    cause: str
    basis: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class TriageResult(BaseModel):
    """分诊输出契约（JSON 报告的 schema）。"""

    test_id: str
    classification: dict[str, Any]
    suspected_module: str = ""
    key_evidence: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=5)
    missing_info: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    defect_candidate: bool = False
    conclusion: str = "hypothesis_needs_human_confirmation"
    analysis_source: str = "rules_only"        # rules_only | llm+rules
    signature: str = ""                         # 归因签名（同因失败聚合）
    duplicate_of: str | None = None             # 前面同签名的 test_id

    model_config = {"protected_namespaces": ()}


def _sig(test_id: str, causes: list[str]) -> str:
    """归因签名：把假设文本归一化做 sha1——同一批失败里"同因"聚合。"""
    import hashlib

    norm = "|".join(c.strip().lower()[:80] for c in sorted(set(causes)))
    if not norm:
        norm = test_id
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


# 分类 → 固定分析模板（规则_only 模式的可解释结论）
_TEMPLATES: dict[str, tuple[str, list[str], list[str], bool]] = {
    "environment_issue": (
        "环境/网络",
        ["后端进程未启动或容器未就绪（compose up 未完成）",
         "网关/端口转发问题导致连接被拒"],
        ["确认 docker compose ps 与后端健康检查",
         "重跑该用例并观察 gates.ensure_backend_ready 日志"],
        False,
    ),
    "test_data_issue": (
        "测试数据",
        ["触发限流（注册 5 次/小时/IP）或数据冲突（重复注册）",
         "并行用例争抢同一份数据"],
        ["执行 make clean-ratelimit 后重跑",
         "检查该用例是否应改用 uuid 后缀的隔离账号（user_factory）"],
        False,
    ),
    "test_script_issue": (
        "测试代码",
        ["断言键名/契约 schema 与实际响应不一致（接口演化未同步）",
         "client 封装的解析逻辑出错"],
        ["对照 contracts/openapi.yaml 核对字段",
         "修复测试代码或同步契约文件"],
        False,
    ),
    "suspected_code_defect": (
        "后端业务",
        ["服务端返回 5xx/死锁特征（如热门流缓存重建与发布事务互锁）",
         "业务断言失败但请求/响应均有完整现场，行为与契约不符"],
        ["抽取 request_id 查后端日志与慢 SQL",
         "本地最小化复现（单接口重放该请求体）"],
        True,
    ),
    "needs_deep_analysis": (
        "待定（业务状态链路）",
        ["写操作经 RabbitMQ 异步生效，轮询超时可能是消费延迟或消费失败",
         "也可能是产品缺陷导致状态永远不落库"],
        ["查 RabbitMQ 队列堆积与消费者日志",
         "直接查库核对业务表状态，区分'未消费'与'消费了但没生效'"],
        False,
    ),
}


def _module_from_evidence(classification: Classification) -> str:
    """从证据的最后一个 HTTP 交互猜疑似模块（feed/video/...）。"""
    last = classification.signals.get("last_exchange") or {}
    path = last.get("path") or ""
    for prefix in ("/feed", "/video", "/social", "/user", "/bug"):
        if path.startswith(prefix):
            return prefix.lstrip("/") or "root"
    return ""


def _rule_only_result(record, classification: Classification) -> TriageResult:
    """纯规则结论：按分类套固定分析模板（可解释、可预期、零成本）。"""
    module, causes, actions, defect = _TEMPLATES.get(
        classification.category, ("unknown", ["规则未覆盖的分类"], ["人工跟进"], False)
    )
    key_evidence = [
        f"failure_type={record.failure_type}",
        f"message={record.message[:200]}",
    ]
    if classification.signals.get("last_status") is not None:
        key_evidence.append(f"last_status={classification.signals['last_status']}")
    if record.evidence_path:
        key_evidence.append(f"evidence={Path(record.evidence_path).name}")
    else:
        key_evidence.append("evidence=未捕获（evidence 插件未启用或目录未挂载）")
    return TriageResult(
        test_id=record.test_id,
        classification=classification.to_dict(),
        suspected_module=module,
        key_evidence=key_evidence,
        hypotheses=[
            Hypothesis(cause=c, basis="规则分类模板", confidence=classification.confidence)
            for c in causes
        ],
        missing_info=[] if record.evidence_path else ["缺少执行现场证据（api_exchanges/poll_history）"],
        recommended_actions=actions,
        defect_candidate=defect,
        analysis_source="rules_only",
        signature=_sig(record.test_id, causes),
    )


def _llm_enrichment(record, result: TriageResult, gateway: LLMGateway) -> TriageResult:
    """把规则结论 + 脱敏证据交给 LLM 归因；任何异常静默回退 rules_only。"""
    evidence = deep_redact(record.evidence) if record.evidence else None
    user_payload = {
        "test": {
            "test_id": record.test_id,
            "failure_type": record.failure_type,
            "message": record.message[:800],
        },
        "rule_classification": result.classification,
        "evidence": evidence,
    }
    try:
        data = gateway.chat_json(
            TRIAGE_SYSTEM_PROMPT, json.dumps(user_payload, ensure_ascii=False)
        )
        result.suspected_module = data.get("suspected_module") or result.suspected_module
        hyps = [
            Hypothesis.model_validate(h)
            for h in data.get("hypotheses", [])[:3]
            if isinstance(h, dict)
        ]
        if hyps:
            result.hypotheses = hyps
        result.missing_info = data.get("missing_info") or result.missing_info
        result.recommended_actions = data.get("recommended_actions") or result.recommended_actions
        result.defect_candidate = bool(data.get("defect_candidate", result.defect_candidate))
        result.analysis_source = "llm+rules"
        result.signature = _sig(record.test_id, [h.cause for h in result.hypotheses])
    except (OfflineModeError, GatewayError, ValueError, KeyError):
        # LLM 不可用 → 保持 rules_only 结论（分诊永不因 AI 故障而失败）
        pass
    return result


def analyze(record, classification: Classification, gateway: LLMGateway | None = None) -> TriageResult:
    """单条失败的分诊分析主入口。"""
    result = _rule_only_result(record, classification)
    module = _module_from_evidence(classification)
    if module:
        result.suspected_module = module
    if gateway is not None and gateway.mode == "remote":
        result = _llm_enrichment(record, result, gateway)
    return result


def dedup(results: list[TriageResult]) -> list[TriageResult]:
    """同签名聚合：第一条保留完整结论，后续标记 duplicate_of。"""
    seen: dict[str, str] = {}
    for r in results:
        first = seen.get(r.signature)
        if first:
            r.duplicate_of = first
        else:
            seen[r.signature] = r.test_id
    return results

