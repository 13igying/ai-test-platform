"""AI 生成用例的执行层：把"已批准"的 AI 用例真正跑进 pytest 回归。

流程闭环（《改进方案》4.1 第五层"人工评审后进执行"）：
  cli generate/demo 产出候选 → 人工评审 → cli promote 登记签名
  → 本文件在收集期按签名过滤，只执行已批准用例 → 运行轨迹进 Allure。

因此：没有 promote 过任何用例时，整个文件 skip（CI 不误报）；
promote 后，AI 用例与手写用例同台回归、失败同样进分诊流水线。
"""
from __future__ import annotations

import json

import pytest

from ai.case_generation.cli import GENERATED_DIR, load_approved_signatures
from ai.case_generation.registry import CaseContext, run_case
from ai.case_generation.schema import GeneratedCase
from ai.case_generation.validator import validate_case
from framework.fixtures import make_anon_client


def load_approved_cases() -> list[GeneratedCase]:
    """扫描候选文件，挑出通过校验且签名已在批准库中的用例。"""
    sigs = load_approved_signatures()
    cases: list[GeneratedCase] = []
    for f in sorted(GENERATED_DIR.glob("*.json")):
        try:
            raws = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raws = raws.get("cases", []) if isinstance(raws, dict) else raws
        for raw in raws:
            res = validate_case(raw)
            if res.ok and res.signature in sigs:
                cases.append(res.case)
    return cases


APPROVED_CASES = load_approved_cases()


@pytest.mark.skipif(
    not APPROVED_CASES,
    reason="无已批准的 AI 生成用例：先运行 `python -m ai.case_generation.cli demo && ... promote`",
)
@pytest.mark.parametrize("case", APPROVED_CASES, ids=[c.case_id for c in APPROVED_CASES])
def test_ai_generated_case(case: GeneratedCase, api_base_url, module_user):
    """执行一条 AI 生成用例（precondition → steps → assertions）。"""
    anon = make_anon_client(api_base_url)
    ctx = CaseContext(
        base_url=api_base_url,
        client=module_user.client,
        anon_client=anon,
        author=module_user,
    )
    try:
        run_case(case, ctx)
    finally:
        anon.close()
