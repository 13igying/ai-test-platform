"""AI 失败分诊 CLI（对应《改进方案》5.4 的落地入口）。

用法：
  python -m ai.failure_triage.cli --junit reports/junit.xml --evidence-dir reports/evidence --out ai_data/triage
  python -m ai.failure_triage.cli --demo     # 内置演示（离线可跑，含计划 5.4 的死锁场景）

产物：triage_report.json（机器可读）+ triage_report.md（人读）。
设计承诺：分诊永不因 AI 故障而失败——LLM 不可用时整批降级 rules_only。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai.case_generation.gateway import LLMGateway
from ai.failure_triage.analyzer import analyze, dedup
from ai.failure_triage.classifier import classify
from ai.failure_triage.collector import collect, extract_signals

_DEMO_DIR = Path(__file__).parent / "demo"


def triage(junit_path: Path, evidence_dir: Path | None, gateway: LLMGateway | None) -> list:
    """collect → classify → analyze → dedup 的主编排。"""
    records = collect(junit_path, evidence_dir)
    results = []
    for rec in records:
        cls = classify(rec, extract_signals(rec))
        results.append(analyze(rec, cls, gateway))
    return dedup(results)


def write_reports(results: list, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "triage_report.json"
    md_path = out_dir / "triage_report.md"

    json_path.write_text(
        json.dumps({"results": [r.model_dump() for r in results]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = ["# 失败分诊报告", "", f"共 {len(results)} 条失败", ""]
    for r in results:
        dup = f"（同因重复：{r.duplicate_of}）" if r.duplicate_of else ""
        lines += [
            f"## {r.test_id}{dup}",
            f"- 分类：{r.classification['category']}（置信度 {r.classification['confidence']}，规则 {r.classification['rule']}）",
            f"- 分析来源：{r.analysis_source}｜疑似模块：{r.suspected_module}｜缺陷候选：{'是' if r.defect_candidate else '否'}",
            "- 关键证据：" + "；".join(r.key_evidence),
            "- 假设：",
        ]
        for i, h in enumerate(r.hypotheses, 1):
            lines.append(f"  {i}. {h.cause}（依据：{h.basis}，置信 {h.confidence}）")
        lines.append("- 建议动作：" + "；".join(r.recommended_actions))
        if r.missing_info:
            lines.append("- 缺失信息：" + "；".join(r.missing_info))
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai.failure_triage", description="AI 失败分诊 CLI")
    parser.add_argument("--junit", help="pytest junit XML 路径")
    parser.add_argument("--evidence-dir", default="reports/evidence", help="失败证据目录")
    parser.add_argument("--out", default="ai_data/triage", help="报告输出目录")
    parser.add_argument("--demo", action="store_true", help="运行内置离线演示")
    args = parser.parse_args(argv)

    if args.demo:
        junit, evidence_dir = _DEMO_DIR / "junit_demo.xml", _DEMO_DIR
    elif args.junit:
        junit, evidence_dir = Path(args.junit), Path(args.evidence_dir)
    else:
        parser.error("需要 --junit 或 --demo")

    gateway = LLMGateway()
    mode = "remote" if gateway.mode == "remote" else "offline(rules_only)"
    results = triage(junit, evidence_dir, gateway)
    json_path, md_path = write_reports(results, Path(args.out))

    defect_n = sum(1 for r in results if r.defect_candidate)
    dup_n = sum(1 for r in results if r.duplicate_of)
    print(f"[failure_triage] LLM 模式: {mode}；失败 {len(results)} 条")
    for r in results:
        dup = f" (同因重复→{r.duplicate_of})" if r.duplicate_of else ""
        print(f"  - {r.test_id}: {r.classification['category']}{dup}"
              f" | 缺陷候选={r.defect_candidate} | 来源={r.analysis_source}")
    print(f"  缺陷候选 {defect_n} 条（须人工确认后上报）")
    print(f"  报告: {json_path}")
    print(f"  报告: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
