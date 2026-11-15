"""AI 用例生成 CLI（对应《改进方案》4.1 的落地入口）。

用法：
  python -m ai.case_generation.cli demo               # 离线全流程演示（CI/无 Key 可跑）
  python -m ai.case_generation.cli generate --n 8     # LLM 生成（未配置 Key 自动降级）
  python -m ai.case_generation.cli validate --file candidates.json
  python -m ai.case_generation.cli promote --file candidates.json  # 人工评审后登记

产物目录：ai_data/generated/（候选）、ai_data/approved/（已批准签名库）。
流程强调"AI 只到候选为止"：promote 必须人工触发，登记后才算进入用例库。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ai.case_generation.evaluator import evaluate
from ai.case_generation.generator import llm_feed_cursor_cases, offline_feed_cursor_cases
from ai.case_generation.gateway import GatewayError, LLMGateway, OfflineModeError
from ai.case_generation.validator import validate_batch

AI_DATA_DIR = Path(__file__).resolve().parents[2] / "ai_data"
GENERATED_DIR = AI_DATA_DIR / "generated"
APPROVED_DIR = AI_DATA_DIR / "approved"
SIGNATURES_FILE = APPROVED_DIR / "signatures.txt"


def load_approved_signatures() -> set[str]:
    if SIGNATURES_FILE.exists():
        return set(SIGNATURES_FILE.read_text(encoding="utf-8").split())
    return set()


def load_raw(path: Path) -> list[dict[str, Any]]:
    raws = json.loads(path.read_text(encoding="utf-8"))
    return raws.get("cases", []) if isinstance(raws, dict) else raws


def save_candidates(cases: list[dict[str, Any]], name: str) -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / name
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def report(raw: list[dict[str, Any]], source: str, out: Path) -> None:
    metrics = evaluate(raw, approved_signatures=load_approved_signatures())
    print(f"[case_generation] 生成来源: {source}；候选文件: {out}")
    print(f"  候选总数 {metrics.total} | 结构有效率 {metrics.structural_validity_rate:.0%}"
          f" | 业务有效率 {metrics.business_validity_rate:.0%}"
          f" | 去重率 {metrics.dedup_rate:.0%} | 覆盖增量 {metrics.coverage_increment}")
    for s in metrics.invalid_samples:
        print(f"  [无效样本] {s['case_id']}: {s['errors']}")


def cmd_demo(args) -> int:
    """离线全流程：确定性生成 → 校验 → 去重 → 评估 → 落盘。"""
    raw = offline_feed_cursor_cases()
    out = save_candidates(raw, "feed_cursor_candidates.json")
    report(raw, "offline(确定性模板)", out)
    return 0


def cmd_generate(args) -> int:
    """LLM 生成路径；offline/网关失败时给出明确降级提示（不崩溃）。"""
    gateway = LLMGateway()
    if gateway.mode == "offline":
        print("[case_generation] 未配置 AI_LLM_BASE_URL/AI_LLM_API_KEY → 自动降级 offline")
        raw, source = offline_feed_cursor_cases()[: max(args.n, 1)], "offline(降级)"
    else:
        print(f"[case_generation] LLM 模式：model={gateway.model}")
        try:
            raw, source = llm_feed_cursor_cases(gateway, count=args.n), "llm"
        except (OfflineModeError, GatewayError) as err:
            print(f"[case_generation] LLM 调用失败（{err}）→ 降级 offline 生成")
            raw, source = offline_feed_cursor_cases()[: max(args.n, 1)], "offline(降级)"
    out = save_candidates(raw, "llm_candidates.json" if source == "llm" else "offline_candidates.json")
    report(raw, source, out)
    return 0


def cmd_validate(args) -> int:
    raws = load_raw(Path(args.file))
    results = validate_batch(raws)
    passed = sum(1 for r in results if r.ok)
    print(f"[case_generation] 校验 {len(results)} 条：通过 {passed}，失败 {len(results) - passed}")
    for raw, res in zip(raws, results):
        if not res.ok:
            print(f"  ✗ {raw.get('case_id')}: {res.first_error()}")
    return 0 if passed == len(results) else 1


def cmd_promote(args) -> int:
    """人工评审通过后：把用例签名登记进批准库（幂等）。"""
    results = validate_batch(load_raw(Path(args.file)))
    approved = load_approved_signatures()
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    added = 0
    with SIGNATURES_FILE.open("a", encoding="utf-8") as fh:
        for res in results:
            if res.ok and res.signature not in approved:
                fh.write(res.signature + "\n")
                approved.add(res.signature)
                added += 1
    print(f"[case_generation] 已登记 {added} 条签名到 {SIGNATURES_FILE}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai.case_generation", description="AI 用例生成 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="离线全流程演示")
    p_gen = sub.add_parser("generate", help="LLM 生成（自动降级）")
    p_gen.add_argument("--n", type=int, default=6, help="生成条数")
    p_val = sub.add_parser("validate", help="校验候选文件")
    p_val.add_argument("--file", required=True)
    p_pro = sub.add_parser("promote", help="人工评审后登记签名")
    p_pro.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    return {
        "demo": cmd_demo,
        "generate": cmd_generate,
        "validate": cmd_validate,
        "promote": cmd_promote,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
