"""AI 用例生成模块的离线单元测试（无后端、无真实 LLM）。"""
from __future__ import annotations

import json

import httpx
import pytest
from framework.config import Settings

from ai.case_generation.evaluator import evaluate
from ai.case_generation.gateway import (
    GatewayError,
    LLMGateway,
    OfflineModeError,
    extract_json,
)
from ai.case_generation.generator import llm_feed_cursor_cases, offline_feed_cursor_cases
from ai.case_generation.schema import signature_of
from ai.case_generation.validator import validate_batch, validate_case


def _good_case() -> dict:
    return {
        "case_id": "feed_latest_first_page_normal",
        "api": "POST /feed/listLatest",
        "category": "normal",
        "steps": ["fetch_first_page"],
        "assertions": ["page_size_respected"],
        "params": {"limit": 10},
    }


def test_offline_generator_fully_valid():
    cases = offline_feed_cursor_cases()
    assert len(cases) >= 6
    results = validate_batch(cases)
    for raw, res in zip(cases, results):
        assert res.ok, f"{raw['case_id']}: {res.first_error()}"
    # 确定性生成不应有语义重复
    sigs = {r.signature for r in results}
    assert len(sigs) == len(cases)


def test_signature_ignores_notes_and_source():
    a = dict(_good_case(), notes="A", source="offline")
    b = dict(_good_case(), notes="B", source="llm")
    assert signature_of(a) == signature_of(b)
    c = dict(_good_case(), params={"limit": 20})
    assert signature_of(a) != signature_of(c)


def test_validator_structural_errors_come_from_pydantic():
    res = validate_case({**_good_case(), "unexpected_field": 1})
    assert res.structural_errors and not res.business_errors
    assert not res.structurally_valid

    res = validate_case({**_good_case(), "case_id": "Bad-Case-Id"})
    assert any("case_id" in e for e in res.structural_errors)


def test_validator_business_errors_whitelist():
    res = validate_case(
        {**_good_case(), "steps": ["made_up_step"], "assertions": ["nope"], "api": "DELETE /feed/x"}
    )
    assert res.structurally_valid
    joined = " ".join(res.business_errors)
    assert "made_up_step" in joined and "nope" in joined and "DELETE" in joined


def test_validator_param_key_and_limit_type():
    res = validate_case({**_good_case(), "params": {"evil": 1}})
    assert any("非法参数键" in e for e in res.business_errors)
    res = validate_case({**_good_case(), "params": {"limit": "10"}})
    assert any("limit" in e for e in res.business_errors)
    # 越界 limit 是被测行为（故意传 51），不应误报
    ok_res = validate_case({**_good_case(), "params": {"limit": 51}})
    assert ok_res.ok


def test_validator_dependency_warnings():
    res = validate_case(
        {
            "case_id": "overlap_without_page2",
            "api": "POST /feed/listLatest",
            "category": "consistency",
            "steps": ["fetch_first_page"],
            "assertions": ["no_overlap_between_pages"],
            "params": {},
        }
    )
    assert res.ok  # 警告不阻断
    assert any("fetch_next_page" in w for w in res.warnings)


def test_evaluator_metrics_math():
    good = _good_case()
    dup = dict(good, notes="duplicate")
    bad_struct = {**good, "case_id": "abc", "extra": 1}
    bad_biz = {**good, "case_id": "biz_bad", "steps": ["nope"]}
    # 签名只看语义字段（api/steps/assertions/params...），case_id 不参与——
    # "改个 case_id"的同语义用例在评估口径里就是重复；approved 库按签名比对，
    # 这里预置一条 limit=20 的同构用例（batch 之外的签名），验证已批准库路径。
    already = {**good, "case_id": "other_id", "params": {"limit": 20}}
    batch = [good, dup, bad_struct, bad_biz, already]
    approved = {signature_of(already)}

    m = evaluate(batch, approved_signatures=approved)
    assert m.total == 5
    assert m.structural_valid == 4
    assert m.business_valid == 3
    assert m.duplicates == 2  # dup（批内）+ already（已批准库）
    assert m.unique_valid == 1
    assert m.coverage_increment == 1
    assert m.structural_validity_rate == pytest.approx(0.8)
    assert m.business_validity_rate == pytest.approx(0.75)
    # Metrics 对比率做了 4 位小数舍入
    assert m.dedup_rate == pytest.approx(2 / 3, abs=1e-3)
    assert len(m.invalid_samples) == 2


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('前缀说明 [{"a": 1}] 后缀') == [{"a": 1}]
    with pytest.raises(GatewayError):
        extract_json("完全没有 JSON")
    with pytest.raises(GatewayError):
        extract_json(None)


def test_gateway_offline_mode_raises():
    gw = LLMGateway(settings=Settings())
    assert gw.mode == "offline"
    with pytest.raises(OfflineModeError):
        gw.chat_json("sys", "user")


def test_gateway_remote_via_mock_transport():
    case = dict(_good_case())  # LLM 返回一个合法用例
    content = "```json\n" + json.dumps({"cases": [case]}, ensure_ascii=False) + "\n```"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    gw = LLMGateway(settings=Settings(llm_base_url="http://fake/v1", llm_api_key="k", llm_model="m"))
    assert gw.mode == "remote"
    gw.with_transport(httpx.MockTransport(handler))
    cases = llm_feed_cursor_cases(gw, count=1)
    assert len(cases) == 1
    assert cases[0]["source"] == "llm"
    assert cases[0]["case_id"] == "feed_latest_first_page_normal"
