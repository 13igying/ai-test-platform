"""生成用例的数据契约：Pydantic 结构校验是 AI 产出的第一道闸门。

为什么用 extra="forbid"：LLM 很爱"自由发挥"加字段（如 confidence、
reason、steps 列表套列表）。结构校验必须在进入业务校验前就把
这些产物拦下——结构不合法的候选根本不配占用业务校验的时间。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# 允许生成的目标接口（白名单的第一层：API 级）
ALLOWED_APIS: frozenset[str] = frozenset(
    {
        "POST /feed/listLatest",
        "POST /feed/listLikesCount",
        "POST /feed/listByFollowing",
        "POST /feed/listByTag",
    }
)

CaseCategory = Literal["normal", "boundary", "negative", "consistency", "auth"]


class GeneratedCase(BaseModel):
    """一条 AI 生成的测试用例（结构契约）。

    steps / assertions 只允许引用 registry.py 白名单里的动作名，
    业务校验（validator.py）会逐一核对——结构合法 ≠ 业务可执行。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$", description="snake_case 唯一标识")
    api: str = Field(description="目标接口，必须在 ALLOWED_APIS 白名单内")
    category: CaseCategory
    risk: str = Field(default="pagination", description="风险主题（用于报告聚类）")
    precondition: str | None = Field(default=None, description="前置数据动作（白名单内）")
    steps: list[str] = Field(min_length=1, max_length=8, description="执行步骤（白名单内）")
    assertions: list[str] = Field(min_length=1, max_length=8, description="断言（白名单内）")
    params: dict[str, Any] = Field(default_factory=dict, description="步骤参数（limit 等）")
    notes: str = ""
    source: Literal["offline", "llm"] = "offline"


@dataclass
class ValidationResult:
    """单条候选的校验结论（两级错误分开计数，供评估指标用）。"""

    structural_errors: list[str] = field(default_factory=list)
    business_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signature: str = ""
    case: GeneratedCase | None = None

    @property
    def ok(self) -> bool:
        return not self.structural_errors and not self.business_errors

    @property
    def structurally_valid(self) -> bool:
        return not self.structural_errors

    def first_error(self) -> str:
        errs = self.structural_errors + self.business_errors
        return errs[0] if errs else ""


def canonical_payload(raw: dict[str, Any]) -> str:
    """候选的规范化 JSON（参与去重签名的字段，忽略 notes/source 等无关字段）。"""
    keys = ("api", "category", "precondition", "steps", "assertions", "params")
    canonical = {k: raw.get(k) for k in keys}
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def signature_of(raw: dict[str, Any]) -> str:
    """去重签名：语义相同的用例（仅 notes/source 不同）签名一致。"""
    return hashlib.sha1(canonical_payload(raw).encode("utf-8")).hexdigest()[:16]


def parse_case(raw: dict[str, Any]) -> tuple[GeneratedCase | None, list[str]]:
    """结构校验：返回 (模型实例, 结构错误列表)。"""
    try:
        return GeneratedCase.model_validate(raw), []
    except ValidationError as err:
        errors = []
        for e in err.errors():
            loc = ".".join(str(p) for p in e["loc"]) or "(root)"
            errors.append(f"{loc}: {e['msg']}")
        return None, errors
