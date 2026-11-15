"""两级校验器：结构（Pydantic）→ 业务规则（白名单 + business_rules）→ 去重签名。"""
from __future__ import annotations

from typing import Any

from ai.case_generation.registry import ASSERTIONS, PRECONDITIONS, STEPS
from ai.case_generation.schema import (
    ALLOWED_APIS,
    ValidationResult,
    parse_case,
    signature_of,
)

# params 合法键集（来自 business_rules/feed_rules.yaml 的 param_keys）
ALLOWED_PARAM_KEYS = frozenset(
    {"limit", "latest_time", "likes_count_before", "id_before", "tag_name", "count"}
)


def validate_case(raw: dict[str, Any]) -> ValidationResult:
    """校验单条候选；两级错误分开记录（评估指标需要分母不同的两个率）。"""
    result = ValidationResult()

    # 第一级：结构校验（Pydantic）
    case, structural_errors = parse_case(raw)
    result.structural_errors = structural_errors
    result.signature = signature_of(raw)  # 结构坏了也有签名，重复候选同样能去重
    if case is None:
        return result

    result.case = case

    # 第二级：业务规则校验
    if case.api not in ALLOWED_APIS:
        result.business_errors.append(
            f"api 不在白名单: {case.api!r}（允许: {sorted(ALLOWED_APIS)}）"
        )
    if case.precondition and case.precondition not in PRECONDITIONS:
        result.business_errors.append(
            f"未知 precondition: {case.precondition!r}（白名单: {sorted(PRECONDITIONS)}）"
        )
    unknown_steps = [s for s in case.steps if s not in STEPS]
    if unknown_steps:
        result.business_errors.append(
            f"未知 step: {unknown_steps}（白名单: {sorted(STEPS)}）"
        )
    unknown_asserts = [a for a in case.assertions if a not in ASSERTIONS]
    if unknown_asserts:
        result.business_errors.append(
            f"未知 assertion: {unknown_asserts}（白名单: {sorted(ASSERTIONS)}）"
        )
    bad_keys = [k for k in case.params if k not in ALLOWED_PARAM_KEYS]
    if bad_keys:
        result.business_errors.append(f"非法参数键: {bad_keys}（允许: {sorted(ALLOWED_PARAM_KEYS)}）")
    limit = case.params.get("limit")
    if limit is not None:
        # 越界 limit 是"被测行为"（boundary 用例故意传 51），但类型必须合法
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            result.business_errors.append(f"params.limit 必须是 1..100 的整数: {limit!r}")
    # step → 断言依赖粗检：翻页断言需要先翻页
    needs_page2 = {"no_overlap_between_pages", "cursor_progresses"}
    if needs_page2 & set(case.assertions) and "fetch_next_page" not in case.steps:
        result.warnings.append("断言需要第二页数据，但 steps 中没有 fetch_next_page")
    if "page_size_respected" in case.assertions and "limit" not in case.params:
        result.warnings.append("page_size_respected 未显式给 params.limit，按默认 10 断言")

    return result


def validate_batch(candidates: list[dict[str, Any]]) -> list[ValidationResult]:
    """批量校验（保持输入顺序）。"""
    return [validate_case(c) for c in candidates]
