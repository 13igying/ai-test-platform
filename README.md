# ai-test-platform

`feedsystem_video_go`（Go + Vue 3 短视频 Feed 系统）的**独立测试平台仓库**：测试框架、AI 用例生成、AI 失败分诊、性能压测与 CI 全部集中在此，被测系统（SUT）留在 `feedsystem_video_go` 仓库。

## 定位

- **离线优先**：`pytest tests/unit`（46 用例）与两个 AI CLI demo 无后端、无 LLM Key 即可完整运行。
- **AI 平台**：对应《改进方案》4.1（AI 生成用例）与 5.4（AI 失败分诊），规则模板保底、LLM 可选增强，AI 故障不影响测试主流程。
- **与环境解耦**：所有可变参数走环境变量（`framework/config.py`），本地 / Docker / CI 零改动切换。

## 目录结构

```
ai-test-platform/
├── tests/              # 用例：api / security / integration / unit / e2e + tools
│   ├── api/            # 接口回归（pytest + framework 客户端）
│   ├── security/       # 越权/鉴权矩阵（29 条路由，参数化）
│   ├── integration/    # 跨服务异步链路（点赞计数、关注流、评论可见性）
│   ├── unit/           # 框架/AI 模块离线单测
│   ├── e2e/            # Playwright UI 冒烟
│   ├── tools/          # junit_summary 等 CI 辅助脚本
│   ├── gates.py        # 就绪门禁（后端 /healthz、前端探活，fail fast）
│   └── run_allure.*    # 一键 Allure 报告（五步法第四+五步）
├── framework/          # 自研测试框架：clients（SystemClient + 子 API）、
│                       # data_factory、assertions（eventual/schema）、
│                       # observability（失败证据落盘 + 脱敏 + Allure 扩展 + pytest 插件）
├── ai/                 # AI 平台（详见 ai/README.md）
│   ├── case_generation/  # LLM 网关 / 生成 / 校验 / 去重 / 评估 / 注册表
│   └── failure_triage/   # 采集 → 规则分类 → 深度归因 → 报告
├── performance/        # Locust 压测（读写 4:1，遵守 30 次/分钟写限流）
├── business_rules/     # 业务规则声明（用例生成的白名单依据）
├── contracts/          # openapi.yaml 接口契约
├── postman/            # 手工联调用 Postman 集合
├── conftest.py         # 注册全局 pytest 插件（失败证据采集）
├── pytest.ini          # 根配置与 markers
└── requirements.txt    # 统一依赖
```

## 快速开始

```bash
# 安装依赖（Python 3.11+）
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # Linux/macOS

# 1. 离线单元测试（无需任何服务）
pytest tests/unit

# 2. AI 用例生成离线演示 → ai_data/generated/
python -m ai.case_generation.cli demo

# 3. AI 失败分诊离线演示 → ai_data/triage_demo/
python -m ai.failure_triage.cli --demo --out ai_data/triage_demo

# 4. 真实回归（需先启动 SUT：在 feedsystem_video_go 仓库 docker compose up -d）
$env:API_BASE_URL='http://127.0.0.1:8080'       # Windows PowerShell
pytest tests/api tests/security tests/integration -q

# 5. 对真实失败出 AI 分诊报告
python -m ai.failure_triage.cli --junit reports/junit.xml --evidence-dir reports/evidence --out ai_data/triage

# 6. 性能压测（可选）
locust -f performance/locustfile.py --headless -u 50 -r 5 -t 1m --host http://127.0.0.1:8080

# 7. E2E（可选）：pip install playwright && playwright install chromium
$env:FRONTEND_URL='http://127.0.0.1:5173'; pytest tests/e2e
```

环境变量（全部可选）：`API_BASE_URL`（默认 127.0.0.1:8080）、`FRONTEND_URL`（默认 127.0.0.1:5173）、`API_TIMEOUT`、`REPORTS_DIR`、`AI_LLM_BASE_URL` / `AI_LLM_API_KEY` / `AI_LLM_MODEL`（未配置即离线模式）。

## CI

| Workflow | 内容 |
|---|---|
| `ci.yml` → **unit-offline** | 离线单测 + 两个 AI demo，上传 `ai_data/`、junit 产物 |
| `ci.yml` → **api-regression** | checkout SUT 仓库 → `docker compose --wait` 拉起全栈 → API/安全/集成回归 → `if: always()` AI 分诊出报告 |
| `api-tests.yml` | 拉起完整栈（含 feishu-mock）→ API 回归 → Allure HTML → Job Summary |

被测系统仓库默认取**同 owner 的 `feedsystem_video_go`**；如 remote 命名不同，在仓库 Settings → Variables 配置 `SUT_REPOSITORY`（形如 `owner/name`）即可，无需改 workflow。

## 数据流

```
pytest 运行 ──► reports/junit.xml（失败清单）
             └► reports/evidence/*.json（EvidenceStore 现场证据，已脱敏）
                        │
        collector ─► classifier（规则分类）─► analyzer（LLM 可选归因）
                        │
                ai_data/triage*/triage_report.{json,md}
```

详细设计见 [`ai/README.md`](ai/README.md) 与 [`tests/README.md`](tests/README.md)。
