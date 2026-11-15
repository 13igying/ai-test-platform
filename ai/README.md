# AI 测试平台（AI 用例生成 + AI 失败分诊）

对应《改进方案》4.1（AI 生成用例）与 5.4（AI 失败分诊）。**离线优先**：不配置 LLM key 时全流程可完整运行（规则模板 / 本地生成），配置后自动切换 LLM 增强，任何 AI 故障都不会让测试或分诊流程失败。

## 目录结构

```
ai/
├── case_generation/        # 4.1 AI 用例生成
│   ├── gateway.py          # LLM 网关（唯一出口，OpenAI 兼容协议，换模型只改环境变量）
│   ├── generator.py        # 用例生成器（离线模板 / LLM 两种模式）
│   ├── validator.py        # 契约校验（字段、路由、参数合法性）
│   ├── evaluator.py        # 去重与指标（dedup_rate / novelty 等）
│   ├── registry.py         # 已批准用例注册表（approved 签名去重）
│   ├── schema.py           # 用例数据结构
│   ├── prompts/feed_cursor_v1.md   # feed 游标分页用例的 prompt 模板
│   └── cli.py              # 命令行入口
├── failure_triage/         # 5.4 AI 失败分诊
│   ├── collector.py        # 采集 junit.xml + reports/evidence/ 现场证据
│   ├── classifier.py       # 规则分类（代码缺陷 / 环境问题 / 用例问题）
│   ├── analyzer.py         # 深度归因（规则结论 + 可选 LLM，静默降级 rules_only）
│   └── cli.py              # 命令行入口（--demo 内置离线演示）
└── __init__.py
```

## LLM 配置（可选）

网关读取 `AI_LLM_BASE_URL` / `AI_LLM_API_KEY`（OpenAI 兼容 `/chat/completions`）：

```bash
# 未设置 → offline 模式（全流程可用）
# 设置后 → remote 模式（分诊输出 analysis_source=llm+rules）
export AI_LLM_BASE_URL=https://api.openai.com/v1
export AI_LLM_API_KEY=sk-...
```

## 快速开始

```bash
# 1. AI 用例生成演示（离线，产出 ai_data/generated/*.json）
python -m ai.case_generation.cli demo

# 2. 生成 / 校验 / 批准指定条数
python -m ai.case_generation.cli generate --n 6
python -m ai.case_generation.cli validate --file ai_data/generated/xxx.json
python -m ai.case_generation.cli promote --file ai_data/generated/xxx.json

# 3. 失败分诊离线演示（内置 3 条失败样本，产出 ai_data/triage_demo/）
python -m ai.failure_triage.cli --demo --out ai_data/triage_demo

# 4. 对真实失败分诊（CI 中同样用法）
pytest tests/api tests/security tests/integration -q --junitxml=reports/junit.xml
python -m ai.failure_triage.cli --junit reports/junit.xml --evidence-dir reports/evidence --out ai_data/triage
```

## 数据流

```
pytest 运行 ──► reports/junit.xml（失败清单）
             └► reports/evidence/*.json（EvidenceStore 现场证据：请求/响应/轮询历史，已脱敏）
                        │
        collector 聚合 ─► classifier 规则分类 ─► analyzer 深度归因（LLM 可选）
                        │
                ai_data/triage/triage_report.{json,md}
                （分类 / 置信度 / 关键证据 / 假设 / 建议动作 / 同因重复聚合）
```

分诊原则：环境问题（如后端未就绪）不判为缺陷候选；同一根因的失败聚合为一条主记录 + 重复列表。

## 单元测试与 CI

- 离线单测：`pytest tests/unit`（46 个用例，覆盖网关 JSON 提取、分类器、分析器脱敏、指标数学等）。
- CI（`.github/workflows/ci.yml`）：
  - **unit-offline** job：单测 + 两个 AI CLI demo，产物上传 `ai_data/generated/`、`ai_data/triage_ci/`、`reports/junit_unit.xml`。
  - **api-regression** job：API/安全/集成回归后，`if: always()` 执行真实分诊（消费 `reports/junit.xml` + `reports/evidence/`），报告上传为 artifact。
- 性能压测：`performance/locustfile.py`（读写 4:1，FeedReader / FeedInteractor 两个用户类，遵守写接口 30 次/分钟限流）。
