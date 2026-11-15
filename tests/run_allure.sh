#!/usr/bin/env bash
# 一键生成 Allure 接口测试报告（五步法的第四步 + 第五步打包）。
#
# 用法：
#   ./tests/run_allure.sh                                   # 默认 tests/api
#   API_BASE_URL=http://<IP>:8080 ./tests/run_allure.sh     # 指定被测后端
#   ./tests/run_allure.sh tests/api/test_feed.py            # 只跑某模块
#
# 前置（五步法第一步）：
#   pip install allure-pytest
#   npm install -g allure-commandline   # 或 apt/scoop 安装 allure 命令行
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8080}"
TEST_PATH="${1:-tests/api}"

echo "==> 被测后端: $API_BASE_URL"
echo "==> 用例范围: $TEST_PATH"

# ---------- 第四步：执行用例，生成 JSON 数据 ----------
echo ""
echo "==> [第四步] pytest --alluredir=./report 生成 JSON 结果 ..."
pytest "$TEST_PATH" -v --alluredir=./report --clean-alluredir
PYTEST_EXIT=$?   # 有用例失败也继续出报告，报告本身就是用来看失败的

# ---------- 第五步：JSON -> HTML ----------
echo ""
echo "==> [第五步] allure generate ./report -o ./html --clean 生成 HTML 报告 ..."
allure generate ./report -o ./html --clean
if [ $? -ne 0 ]; then
    echo "allure 命令不可用？请先安装：npm install -g allure-commandline" >&2
    exit 1
fi

echo ""
echo "==> 报告已生成: $REPO_ROOT/html/index.html"
echo "    浏览器查看: allure open ./html （或 allure serve ./report）"
exit $PYTEST_EXIT
