"""生成质量评估（改进方案 4.1 第四层）：结构有效率 / 业务有效率 / 去重率 / 覆盖增量。

评估口径（面试可讲）：
- structural_validity_rate：Pydantic 结构校验通过比例——衡量"输出能不能解析"；
- business_validity_rate：结构通过者中业务规则校验通过比例——衡量"懂不懂业务"；
- dedup_rate：语义签名重复比例——衡量"会不会翻来覆去生成同一张脸"；
- coverage_increment：有效候选中"签名未见于已批准集"的比例——衡量
  "这批生成对既有用例库有没有净增量"。四个指标一起看才是质量。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ai.case_generation.validator import validate_batch


@dataclass
class GenerationMetrics:
    total: int = 0
    structural_valid: int = 0
    business_valid: int = 0
    invalid: int = 0
    duplicates: int = 0
    unique_valid: int = 0
    coverage_increment: int = 0
    structural_validity_rate: float = 0.0
    business_validity_rate: float = 0.0
    dedup_rate: float = 0.0
    invalid_samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate(
    candidates: list[dict[str, Any]],
    approved_signatures: set[str] | None = None,
    max_invalid_samples: int = 10,
) -> GenerationMetrics:
    """对一批候选计算指标；approved_signatures 为已批准用例的签名集。"""
    approved_signatures = approved_signatures or set()
    results = validate_batch(candidates)
    m = GenerationMetrics(total=len(candidates))

    seen_signatures: set[str] = set()
    new_signatures: set[str] = set()
    for raw, res in zip(candidates, results):
        if not res.structurally_valid:
            m.invalid += 1
            if len(m.invalid_samples) < max_invalid_samples:
                m.invalid_samples.append(
                    {"case_id": raw.get("case_id"), "errors": res.structural_errors}
                )
            continue
        m.structural_valid += 1

        if not res.ok:
            m.invalid += 1
            if len(m.invalid_samples) < max_invalid_samples:
                m.invalid_samples.append(
                    {"case_id": raw.get("case_id"), "errors": res.business_errors}
                )
            continue
        m.business_valid += 1

        # 去重：批内 + 与已批准集比对
        sig = res.signature
        if sig in seen_signatures or sig in approved_signatures:
            m.duplicates += 1
        else:
            seen_signatures.add(sig)
            m.unique_valid += 1
            if sig not in approved_signatures:
                new_signatures.add(sig)

    m.coverage_increment = len(new_signatures)
    if m.total:
        m.structural_validity_rate = round(m.structural_valid / m.total, 4)
    if m.structural_valid:
        m.business_validity_rate = round(m.business_valid / m.structural_valid, 4)
    if m.business_valid:
        m.dedup_rate = round(m.duplicates / m.business_valid, 4)
    return m
