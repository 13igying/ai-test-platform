"""AI 失败分诊模块的离线单元测试（collector/classifier/analyzer/CLI 演示）。"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from ai.case_generation.gateway import LLMGateway
from framework.config import Settings

from ai.failure_triage.analyzer import analyze, dedup
from ai.failure_triage.cli import main as triage_main
from ai.failure_triage.classifier import (
    C_ANALYZE,
    C_DATA,
    C_DEFECT,
    C_ENV,
    C_SCRIPT,
    classify,
)
from ai.failure_triage.collector import (
    FailureRecord,
    _nodeid_from,
    collect,
    extract_signals,
    sanitize_case_id,
)


def _rec(
    test_id="tests/api/test_feed.py::TestFeed::test_x",
    failure_type="AssertionError",
    message="assert something",
    evidence=None,
    outcome="failed",
) -> FailureRecord:
    return FailureRecord(
        test_id=test_id,
        classname="tests.api.test_feed.TestFeed",
        name="test_x",
        outcome=outcome,
        failure_type=failure_type,
        message=message,
        evidence=evidence,
    )


# ---------------- collector ----------------

def test_nodeid_reconstruction():
    assert _nodeid_from("tests.api.test_feed.TestFeed", "test_x") == (
        "tests/api/test_feed.py::TestFeed::test_x"
    )
    assert _nodeid_from("tests.api.test_feed", "test_y") == "tests/api/test_feed.py::test_y"


def test_sanitize_matches_evidence_dump_rule():
    nodeid = "tests/api/test_x.py::TestY::test_z"
    assert sanitize_case_id(nodeid) == "tests_api_test_x.py__TestY__test_z"


def test_collector_pairs_junit_with_evidence(tmp_path):
    nodeid = "tests/api/test_feed.py::TestFeed::test_x"
    (tmp_path / (sanitize_case_id(nodeid) + ".json")).write_text(
        json.dumps(
            {"api_exchanges": [{"status": 500, "path": "/feed/listLatest"}]}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    junit = tmp_path / "junit.xml"
    junit.write_text(
        """<testsuites><testsuite name="pytest" failures="1" tests="1">
        <testcase classname="tests.api.test_feed.TestFeed" name="test_x" time="1.0">
          <failure message="boom" type="AssertionError">tb</failure>
        </testcase></testsuite></testsuites>""",
        encoding="utf-8",
    )
    records = collect(junit, tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec.test_id == nodeid and rec.outcome == "failed"
    assert rec.evidence["api_exchanges"][0]["status"] == 500

    sig = extract_signals(rec)
    assert sig["last_status"] == 500

    # 证据目录不存在/为空：配不上就明说（evidence=None），不编造


# ---------------- classifier ----------------

def test_classifier_rule_priority():
    cases = [
        (_rec(message="httpx.ConnectError: 连接被拒"), {"last_status": 0}, C_ENV, 0.95),
        (_rec(message="429 限流：注册过于频繁"), {}, C_DATA, 0.85),
        (_rec(failure_type="KeyError", message="KeyError: 'video_list'"), {}, C_SCRIPT, 0.8),
        (_rec(failure_type="WaitTimeoutError", message="等待超时"), {}, C_ANALYZE, 0.5),
        (
            _rec(message="500 — Deadlock found when trying to get lock"),
            {"last_status": 500},
            C_DEFECT,
            0.9,
        ),
        (
            _rec(failure_type="AssertionError", message="assert ids1.isdisjoint(ids2)"),
            {},
            C_DEFECT,
            0.6,
        ),
    ]
    for rec, signals, category, confidence in cases:
        cls = classify(rec, {**extract_signals(rec), **signals})
        assert cls.category == category, rec.message
        assert cls.confidence == confidence


def test_classifier_unclassified_fallback():
    cls = classify(_rec(failure_type="", message="", outcome="error"), {"exception_type": ""})
    assert cls.category == C_ANALYZE


# ---------------- analyzer ----------------

def test_analyzer_rule_only_templates():
    env_cls = classify(_rec(message="ConnectError"), {"last_status": 0})
    res = analyze(_rec(message="ConnectError"), env_cls)
    assert res.analysis_source == "rules_only"
    assert res.conclusion == "hypothesis_needs_human_confirmation"
    assert res.defect_candidate is False

    defect_cls = classify(_rec(message="Deadlock found"), {"last_status": 500})
    res = analyze(_rec(message="Deadlock found"), defect_cls)
    assert res.defect_candidate is True  # 缺陷候选必须人工确认
    assert res.classification["category"] == C_DEFECT

    # 证据里的模块线索（/feed/listLatest）：extract_signals 会把 last_exchange
    # 一并塞进 signals，这里直接构造等价 signals 验证 _module_from_evidence
    evidence = {"api_exchanges": [{"path": "/feed/listLatest", "status": 500}]}
    signals = {"last_status": 500, "last_exchange": {"path": "/feed/listLatest", "status": 500}}
    feed_cls = classify(_rec(message="500", evidence=evidence), signals)
    res = analyze(_rec(message="500", evidence=evidence), feed_cls)
    assert res.suspected_module == "feed"


def test_analyzer_llm_enrichment_redacts_evidence():
    evidence = {
        "api_exchanges": [
            {"path": "/feed", "status": 500, "request_body": {"password": "p1", "limit": 2}}
        ]
    }
    rec = _rec(message="500 Deadlock", evidence=evidence)
    cls = classify(rec, {"last_status": 500})
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        content = json.dumps(
            {
                "suspected_module": "feed",
                "hypotheses": [{"cause": "缓存重建死锁", "basis": "status=500", "confidence": 0.9}],
                "missing_info": ["后端日志"],
                "recommended_actions": ["查慢 SQL"],
                "defect_candidate": True,
            },
            ensure_ascii=False,
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    gw = LLMGateway(settings=Settings(llm_base_url="http://fake/v1", llm_api_key="k", llm_model="m"))
    gw.with_transport(httpx.MockTransport(handler))
    res = analyze(rec, cls, gw)
    assert res.analysis_source == "llm+rules"
    assert res.hypotheses[0].cause == "缓存重建死锁"
    assert res.defect_candidate is True
    # 密码永远不进 LLM 请求体（脱敏是硬约束）
    assert "p1" not in captured["body"]
    assert "******" in captured["body"]


def test_dedup_marks_duplicates():
    cls = classify(_rec(message="Deadlock"), {"last_status": 500})
    r1 = analyze(_rec(message="Deadlock"), cls)
    r2 = analyze(_rec(test_id="tests/api/test_feed.py::TestFeed::test_y", message="Deadlock"), cls)
    dedup([r1, r2])
    assert r2.duplicate_of == r1.test_id
    assert r1.duplicate_of is None


# ---------------- CLI 端到端（离线演示） ----------------

def test_cli_demo_end_to_end(tmp_path, capsys):
    out = tmp_path / "triage"
    assert triage_main(["--demo", "--out", str(out)]) == 0
    report = json.loads((out / "triage_report.json").read_text(encoding="utf-8"))
    results = report["results"]
    assert len(results) == 3  # 两条同因死锁 + 一条环境故障
    assert any(r["defect_candidate"] for r in results)
    assert any(r["duplicate_of"] for r in results)  # 同因聚合
    assert (out / "triage_report.md").exists()
    assert capsys.readouterr().out  # 有摘要输出

    # 同一 junit 配不存在的证据目录：evidence 缺失也要能分诊（降级路径）
    junit = Path(__file__).resolve().parents[2] / "ai" / "failure_triage" / "demo" / "junit_demo.xml"
    assert collect(junit, tmp_path / "nope")[0].evidence is None
