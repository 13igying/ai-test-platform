"""JUnit XML -> Markdown 汇总：给 GitHub Actions Job Summary 用。

标准库实现（xml.etree），零第三方依赖——和自研 Web 运行器同一个思路：
测试资产要能被平台消费，但不为展示引入新依赖。

用法：python tests/tools/junit_summary.py reports/junit.xml
输出直接打印，workflow 里 `>> $GITHUB_STEP_SUMMARY` 即可。
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def summarize(path: str) -> str:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    cost = sum(float(s.get("time", 0)) for s in suites)

    verdict = "✅ 全部通过" if failed + errors == 0 else "❌ 存在失败"
    lines = [
        "## API 测试结果",
        "",
        f"**{verdict}** — 共 {total} 条：失败 {failed} / 错误 {errors} / 跳过 {skipped}，耗时 {cost:.1f}s",
        "",
        "| 用例 | 结果 | 耗时(s) |",
        "|---|---|---|",
    ]
    for suite in suites:
        for case in suite.iter("testcase"):
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            failure = case.find("failure")
            error = case.find("error")
            if failure is not None or error is not None:
                node = failure if failure is not None else error
                msg = (node.get("message") or "").replace("\n", " ")[:160]
                mark = f"❌ {msg}" if msg else "❌"
            elif case.find("skipped") is not None:
                mark = "⚠️ skip"
            else:
                mark = "✅"
            lines.append(f"| `{name}` | {mark} | {float(case.get('time', 0)):.2f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    # Windows 控制台默认 GBK，中文汇总在管道里会 UnicodeDecodeError；强制 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 旧版 Python 无 reconfigure
        pass
    xml_path = sys.argv[1] if len(sys.argv) > 1 else "reports/junit.xml"
    print(summarize(xml_path))