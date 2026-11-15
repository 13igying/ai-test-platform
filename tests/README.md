# 测试套件运行指南

> **典型场景**：项目部署在内网服务器上，您在外网电脑通过浏览器直接访问，**无需拷贝任何代码**。

## 🌐 外网访问（推荐，零拷贝）

服务器通过 Cloudflare Tunnel 把三个服务暴露到公网，您在外网浏览器直接打开即可：

| 服务 | 说明 |
|------|------|
| **Web 测试运行器** | 网页上点按钮跑全部测试 / UI 自动化演示，实时看日志和截图墙 |
| **前端页面** | 直接体验项目本身 |
| **后端 API** | 供本地 Postman/curl 调试 |

### 服务器上启动隧道（一次性操作，管理员执行）

```bash
# 安装 cloudflared（已装可跳过）
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared

# 启动 3 条隧道（后台运行）
/root/feedsystem_video_go/tests/tunnel.sh start

# 查看当前公网地址（每次启动域名随机生成）
/root/feedsystem_video_go/tests/tunnel.sh status
```

> **注意**：quick tunnel 的域名每次重启会变化，把 `tunnel.sh status` 输出的最新地址发给需要访问的人即可。隧道断线会自动重连，但域名不变（进程存活期间）。

### 外网电脑上使用

1. 向管理员要 3 个 `https://xxx.trycloudflare.com` 地址
2. 浏览器打开**运行器**地址 → 网页上直接点按钮运行测试、看实时日志、看 UI 演示截图墙
3. 想本地跑 pytest？无需拷代码，直接指定公网 API 地址：
   ```bash
   pip install pytest requests
   API_BASE_URL=https://<后端隧道地址> pytest <本地测试文件> -v
   ```

## 快速开始（内网电脑 → 服务器）

```bash
# 1. 克隆本仓库到本地（见下方"获取测试代码"）
# 2. 本地装依赖（一次性，仓库根执行）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. API 测试：指向服务器后端
API_BASE_URL=http://45.207.222.231:8080 .venv/bin/pytest tests/api/ -v

# 4. UI 演示：指向服务器前端（本地也需装 Playwright Chromium，见下文）
FRONTEND_URL=http://45.207.222.231:5173 .venv/bin/python ui_demo.py
```

> 把 `45.207.222.231` 换成您服务器的实际 IP/域名。若端口不通，检查服务器防火墙/安全组放行 8080、5173。

## 获取测试代码（克隆到本地电脑）

### 1. 克隆整个测试平台仓库

测试平台已是独立仓库（含 tests/、framework/、ai/ 等），整仓克隆即可：

```bash
# 方式 A：scp 整个仓库（在本地电脑执行）
scp -r <user>@<服务器IP>:/root/ai-test-platform ./ai-test-platform

# 方式 B：git 方式
git clone <ai-test-platform 仓库地址> && cd ai-test-platform
```

### 2. 本地安装依赖（一次性，在仓库根执行）

```bash
python3 -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
# macOS / Linux
.venv/bin/pip install -r requirements.txt
```

### 3. 指向服务器后端并运行

```bash
# macOS / Linux（服务器 IP 示例：45.207.222.231）
API_BASE_URL=http://45.207.222.231:8080 .venv/bin/pytest tests/api/ -v

# Windows PowerShell
$env:API_BASE_URL="http://45.207.222.231:8080"; .venv\Scripts\pytest tests\api\ -v

# Windows CMD
set API_BASE_URL=http://45.207.222.231:8080 && .venv\Scripts\pytest tests\api\ -v
```

> 把 `45.207.222.231` 换成您实际访问服务器的 IP/域名。
> 若走公网或跳板机，可先建 SSH 隧道：`ssh -L 8080:localhost:8080 <user>@<服务器IP>`，然后 `API_BASE_URL=http://127.0.0.1:8080` 即可。

### 4. 常用命令

```bash
# 全部用例（26 核心 + 9 缺陷平台 = 35 条）
API_BASE_URL=http://45.207.222.231:8080 .venv/bin/pytest tests/api/ -v

# 单模块
API_BASE_URL=http://45.207.222.231:8080 .venv/bin/pytest tests/api/test_social.py -v

# 单用例
API_BASE_URL=http://45.207.222.231:8080 .venv/bin/pytest "tests/api/test_social.py::TestLike::test_likes_count_increases" -v

# 生成 HTML 报告
API_BASE_URL=http://45.207.222.231:8080 .venv/bin/pytest tests/api/ -v --html=report.html --self-contained-html
```

## Allure 接口测试报告（五步法）

接口测试报告使用 **Allure** 生成，主要包含五个步骤：

### 第一步：安装插件

```bash
pip install allure-pytest                      # pytest 插件（pytest-allure-adaptor 已废弃）
npm install -g allure-commandline              # Allure 命令行（或 scoop install allure）
```

### 第二步：在用例中添加装饰器

标注用例的**功能模块**（feature）、**故事**（story）、**优先级**（severity），
报告的 Behaviors 视图按 `功能模块 -> 故事` 两级聚类， severity 支持
`blocker / critical / normal / minor / trivial` 五档：

```python
@allure.feature("账号模块")
@allure.story("用户登录")
class TestLogin:
    @allure.severity("blocker")
    def test_login_success(self, anon_client):
        ...
```

### 第三步：关键步骤日志与附件

- `APIClient` 的每个请求自动记录为 `allure.step`，请求体/响应体自动
  `allure.attach` 进报告（失败免复现，点开节点即看现场；token 不进报告）；
- 测试数据工厂的 注册/登录/发布视频、MQ 异步链路的 `wait_until` 轮询
  也都进了步骤树，超时自动标红并附最后观测值；
- 多阶段流程用 `with allure.step("...")` 手工分步（如 Bug 状态机流转）。

### 第四步：执行用例时生成 JSON 数据

```bash
API_BASE_URL=http://45.207.222.231:8080 pytest tests/api/ -v --alluredir=./report
```

### 第五步：生成 HTML 报告

```bash
allure generate ./report -o ./html --clean
allure open ./html        # 起本地服务打开报告（推荐）
```

### 一键脚本

```powershell
# Windows PowerShell
powershell -File tests\run_allure.ps1 -ApiBaseUrl http://45.207.222.231:8080 -Open

# Linux / macOS
API_BASE_URL=http://45.207.222.231:8080 ./tests/run_allure.sh
```

报告里可以看到**用例执行情况、成功率、失败原因、步骤树、请求/响应附件、
环境信息（API_BASE_URL/Python/Host）、Behaviors 功能聚类、severity 分布**等，
非常直观，适合向项目组展示。

> 报告含动态资源，需经 HTTP 服务打开（`allure open` / `allure serve`），
> 直接双击 `html/index.html`（file://）可能白屏。
> CI 已同步集成：`.github/workflows/api-tests.yml` 每次回归自动生成
> Allure 报告并作为 artifact 上传（保留 14 天）。

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_BASE_URL` | `http://127.0.0.1:8080` | 后端 API 地址 |
| `FRONTEND_URL` | `http://127.0.0.1:5173` | 前端地址（E2E 用） |

## CI 集成（GitHub Actions）

`.github/workflows/api-tests.yml` 在 push / PR（`tests/**`、`framework/**`、`ai/**` 变更时）自动执行接口回归；被测系统来自同 owner 的 `feedsystem_video_go` 仓库（CI 中 checkout 到 `sut/`）：

1. `docker compose -f sut/docker-compose.yml up -d --build --wait mysql redis rabbitmq feishu-mock backend worker` —— 与部署同路径拉起全套被测系统，`--wait` 阻塞至全部服务健康
2. `pip install -r requirements.txt`
3. `pytest tests/api/ --junitxml=reports/junit.xml --html=reports/report.html --self-contained-html`（后端就绪兜底探活由 conftest 的 `backend_ready` fixture 负责）
4. `tests/tools/junit_summary.py`（纯标准库）解析 JUnit XML，把总/过/挂/跳 + 每条用例结果写入 **Job Summary**
5. 报告（junit.xml + report.html）上传为 artifact，保留 14 天

本地复现 CI 同款报告：

```bash
pytest tests/api/ --junitxml=reports/junit.xml --html=reports/report.html --self-contained-html
```

## 测试覆盖

- `tests/api/test_account.py` — 注册/登录/鉴权（10 例）
- `tests/api/test_feed.py` — 发布/feed 流/游标分页（9 例）
- `tests/api/test_social.py` — 点赞/取消/关注/粉丝列表，含 MQ 异步轮询（7 例）
- `tests/api/test_bug.py` — 缺陷平台验收：状态机流转/角色过滤/鉴权（9 例）
- `tests/e2e/test_ui_smoke.py` — 前端 E2E 冒烟：注册/登录/推荐/热榜/账号/设置（6 例）

响应结构契约：`tests/api/utils/schemas.py` 用 jsonschema 锁定核心接口的
字段名/类型/嵌套（与后端 entity 逐一核对），通过 `post_ok(..., schema="...")`
自动校验——字段被悄悄改名/改类型时，用例失败信息会精确到 JSON 路径。

注意：测试会向目标服务写入真实数据（注册用户、发布视频），请勿指向生产环境。

## UI 自动化框架（pytest + Playwright + PO 模式）

UI 自动化已重构为标准分层框架，**页面元素定位只维护一份**：

```
tests/e2e/
├── conftest.py        # 浏览器生命周期（session 级启动一次）+ 每用例独立 context + 失败自动截图
├── config.py          # 视口/超时/密码/截图目录等配置
├── pages/             # PO 模式：元素定位与页面操作封装（用例层不碰选择器）
│   ├── base_page.py   # 基类：open / nav / screenshot / url / title
│   ├── register_page.py / account_page.py / feed_page.py / settings_page.py
└── test_ui_smoke.py   # E2E 用例：注册 / 登录 / 推荐 / 热榜 / 账号 / 设置（6 条）
```

框架要点（面试可讲）：

- **PO 模式**：前端改版只需改 `pages/` 对应文件，用例零改动；
- **失败证据链**：用例失败自动全页截图到 `tests/ui_shots/e2e/`，并作为 PNG 附件进 Allure 报告；
- **优雅降级**：未安装 playwright / Chromium 时 E2E 用例自动 skip，不影响 API 用例运行；
- **登录态复用**：`logged_page` 夹具 module 级共享（注册限流友好）；
- **`ui_demo.py` 保留**为 Web 运行器的"演示入口"：复用同一套 `pages/`，
  对外输出（步骤日志 / 截图墙 / `result.json`）契约不变。

### 运行方式

```bash
# 1) pytest 用例（推荐，可进 Allure 报告）
API_BASE_URL=http://45.207.222.231:8080 \
FRONTEND_URL=http://45.207.222.231:5173 pytest tests/e2e -v

# 2) 演示脚本（Web 运行器同款：逐步截图 + result.json）
cd /root/ai-test-platform
FRONTEND_URL=http://45.207.222.231:5173 .venv/bin/python tests/ui_demo.py

# 3) Web 运行器页面点击「🎬 UI 自动化演示」按钮（推荐，可看实时日志 + 截图墙）
# 浏览器打开 http://<服务器IP>:8081
```

### 首次准备（一次性）

```bash
# 安装 playwright pip 包（已包含在 requirements.txt）
.venv/bin/pip install playwright

# 下载 Chromium 浏览器（国内服务器建议用 npmmirror 镜像，速度快）
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
  .venv/bin/playwright install chromium
```

### 本地电脑运行 UI 演示（远程指向服务器）

```bash
# 首次：本地安装 Chromium（国内可用 npmmirror 镜像加速）
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
  .venv/bin/playwright install chromium

# 运行：FRONTEND_URL 指向服务器前端
FRONTEND_URL=http://45.207.222.231:5173 .venv/bin/python ui_demo.py
```

截图保存在本地 `tests/ui_shots/`，`result.json` 为结果摘要。

### 查看结果（服务器上运行时）

- 截图：`tests/ui_shots/*.png`（10 张，覆盖每个操作步骤）
- 结果：`tests/ui_shots/result.json`（每步 ok/detail + 总体 passed）
- E2E 用例失败截图：`tests/ui_shots/e2e/*.png`（全页截图，同时进 Allure 报告附件）
- Web 运行器：点击 UI 演示按钮后，页面下方自动展示截图墙，实时刷新
  （本地电脑浏览器直接访问 `http://<服务器IP>:8081` 即可操作）

