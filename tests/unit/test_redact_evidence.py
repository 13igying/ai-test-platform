"""脱敏与证据模块的离线单元测试。"""
from __future__ import annotations

import json

from ai.failure_triage.collector import sanitize_case_id
from framework.observability.evidence import EvidenceStore
from framework.observability.redact import deep_redact, redact_headers, redact_obj, truncate


# ---------------- 脱敏 ----------------

def test_redact_obj_masks_sensitive_keys_nested():
    data = {
        "username": "alice",
        "password": "secret1",
        "nested": {"access_token": "tok", "list": [{"refresh_token": "r"}]},
        "normal": "keepme",
    }
    out = redact_obj(data)
    assert out["password"] == "******"
    assert out["nested"]["access_token"] == "******"
    assert out["nested"]["list"][0]["refresh_token"] == "******"
    assert out["username"] == "alice"
    assert out["normal"] == "keepme"
    assert data["password"] == "secret1"  # 原对象不被修改


def test_redact_obj_key_substring_hits():
    # 键名包含敏感词即打码（如 x_api_key_v2）
    out = redact_obj({"x_api_key_v2": "k", "myTokenHeader": "t"})
    assert out["x_api_key_v2"] == "******"
    assert out["myTokenHeader"] == "******"


def test_redact_headers_keeps_scheme_only():
    out = redact_headers({"Authorization": "Bearer abc.def.ghi", "Content-Type": "application/json"})
    assert out["Authorization"].startswith("Bearer ")
    assert "abc" not in out["Authorization"]
    assert out["Content-Type"] == "application/json"


def test_deep_redact_present_for_llm_input():
    ev = {"request": {"body": {"password": "p", "limit": 10}}}
    assert deep_redact(ev)["request"]["body"]["password"] == "******"


def test_truncate_marks_overflow():
    text = "x" * 3000
    out = truncate(text, limit=2000)
    assert out.startswith("x" * 10)
    assert "truncated 1000 chars" in out
    assert truncate(None) == ""


# ---------------- 证据 ----------------

def _make_store() -> EvidenceStore:
    s = EvidenceStore()
    s.begin_test("tests/api/test_x.py::TestY::test_z", env={"api_base_url": "http://t"})
    return s


def test_evidence_lifecycle_and_snapshot():
    s = _make_store()
    s.record_exchange({"method": "POST", "path": "/feed/listLatest", "status": 200, "request_id": "rid-1"})
    s.record_exchange({"method": "POST", "path": "/feed/listLatest", "status": 200, "request_id": "rid-1"})
    s.record_poll({"desc": "落库", "attempts": 1, "result": "met"})
    s.note_missing("后端未透传 request_id")
    s.end_test("call", "断言失败示例")

    snap = s.snapshot()
    assert len(snap["api_exchanges"]) == 2
    assert snap["request_ids"] == ["rid-1"]  # 去重
    assert snap["poll_history"][0]["result"] == "met"
    assert snap["missing_evidence"] == ["后端未透传 request_id"]  # 不重复
    assert snap["phase"] == "call"
    assert snap["assertion_error"] == "断言失败示例"


def test_evidence_dump_filename_matches_triage_collector(tmp_path):
    """证据文件名规则必须与 AI 分诊 collector 的 sanitize 完全同构——否则配对失败。"""
    s = _make_store()
    s.record_exchange({"method": "POST", "path": "/x", "status": 200})
    path = s.dump(tmp_path)
    assert path.exists()
    assert path.name == sanitize_case_id("tests/api/test_x.py::TestY::test_z") + ".json"

    # 落盘文件可被 json 解析（分诊 collector 的读取前提）
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["case_id"].endswith("test_z")


def test_evidence_reset_stops_recording():
    s = _make_store()
    s.reset()
    s.record_exchange({"method": "GET", "path": "/y", "status": 200})
    assert s.snapshot() == {"case_id": "(no active case)"}
