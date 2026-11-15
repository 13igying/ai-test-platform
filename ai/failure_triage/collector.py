"""失败分诊阶段 1：证据采集（对应《改进方案》5.4 前半）。

从 pytest 的 junit XML + framework 失败证据目录恢复"失败现场"：
- junit XML 提供失败清单（testcase、failure/error、message、time）；
- reports/evidence/*.json 提供每条失败的深现场（HTTP 交互、轮询记录、
  request_id、证据完整性标注）——collector 按 nodeid 归一化后精确配对。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FailureRecord:
    """一条失败的归一化记录（collector 的输出，classifier/analyzer 的输入）。"""

    test_id: str                 # nodeid 形式：tests/api/test_feed.py::TestX::test_y
    classname: str
    name: str
    outcome: str                 # failed / error
    failure_type: str            # 异常类型（junit type 属性），如 WaitTimeoutError
    message: str                 # 断言/异常文本（截断）
    time_s: float = 0.0
    evidence: dict[str, Any] | None = None
    evidence_path: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)


def sanitize_case_id(case_id: str) -> str:
    """与 framework.observability.evidence.EvidenceStore.dump 同构的文件名归一化。"""
    safe = case_id.replace("::", "__").replace("/", "_")
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in safe)


def _nodeid_from(classname: str, name: str) -> str:
    """junit classname -> nodeid：tests.api.test_feed.TestFeedLatest + test_x
    -> tests/api/test_feed.py::TestFeedLatest::test_x（无类时省略类段）。"""
    parts = classname.split(".") if classname else []
    if parts and parts[-1].startswith("Test"):
        cls, module_parts = parts[-1], parts[:-1]
    else:
        cls, module_parts = None, parts
    if not module_parts:
        return name
    module_path = "/".join(module_parts) + ".py"
    return f"{module_path}::{cls}::{name}" if cls else f"{module_path}::{name}"


def _load_evidence(evidence_dir: Path | None) -> dict[str, tuple[dict, Path]]:
    """目录快照：{sanitized_case_id: (evidence_json, path)}。"""
    out: dict[str, tuple[dict, Path]] = {}
    if evidence_dir is None or not evidence_dir.exists():
        return out
    for p in evidence_dir.glob("*.json"):
        try:
            data = __import__("json").loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out[p.stem] = (data, p)
    return out


def collect(junit_path: str | Path, evidence_dir: str | Path | None = None) -> list[FailureRecord]:
    """解析 junit XML 并配对失败证据；找不到证据时 evidence=None（分诊要声明缺口）。"""
    tree = ET.parse(str(junit_path))
    evidence_map = _load_evidence(Path(evidence_dir) if evidence_dir else None)
    records: list[FailureRecord] = []

    for tc in tree.iter("testcase"):
        node = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        if node is None:
            continue
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        test_id = _nodeid_from(classname, name)
        message = (node.get("message") or node.text or "").strip()
        rec = FailureRecord(
            test_id=test_id,
            classname=classname,
            name=name,
            outcome="failed" if node.tag == "failure" else "error",
            failure_type=node.get("type", ""),
            message=message[:2000],
            time_s=float(tc.get("time") or 0.0),
        )
        ev = evidence_map.get(sanitize_case_id(test_id))
        if ev is not None:
            rec.evidence, rec.evidence_path = ev
        records.append(rec)
    return records


def extract_signals(record: FailureRecord) -> dict[str, Any]:
    """从记录/证据中提取分类特征（classifier 的输入）。"""
    sig: dict[str, Any] = {
        "exception_type": record.failure_type,
        "outcome": record.outcome,
    }
    ev = record.evidence or {}
    exchanges = ev.get("api_exchanges") or []
    if exchanges:
        sig["last_exchange"] = exchanges[-1]
        sig["last_status"] = exchanges[-1].get("status")
    sig["poll_history"] = ev.get("poll_history") or []
    sig["missing_evidence"] = ev.get("missing_evidence") or []
    # message 里可能带状态码（client 的 APIError 文本含 "[响应] 500 ..."）
    import re

    m = re.search(r"\b(\d{3})\b", record.message)
    sig["message_status"] = int(m.group(1)) if m else None
    return sig
