<#
.SYNOPSIS
    一键生成 Allure 接口测试报告（五步法的第四步 + 第五步打包）。

.DESCRIPTION
    用法（在仓库根目录或任意位置执行）：
        powershell -File tests\run_allure.ps1                              # 打本地默认环境
        powershell -File tests\run_allure.ps1 -ApiBaseUrl http://<IP>:8080 # 指定被测后端
        powershell -File tests\run_allure.ps1 -TestPath tests/api/test_feed.py  # 只跑某模块
        powershell -File tests\run_allure.ps1 -Open                        # 跑完自动打开报告

    前置（五步法第一步）：
        pip install allure-pytest      # pytest 插件
        npm install -g allure-commandline   # 或 scoop install allure，提供 allure 命令
#>
param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8080",
    [string]$TestPath = "tests/api",
    [switch]$Open
)

$ErrorActionPreference = "Stop"
# 脚本位于 tests/ 下，仓库根是它的上一级；后续相对路径都按仓库根解析
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:API_BASE_URL) { $env:API_BASE_URL = $ApiBaseUrl }
Write-Host "==> 被测后端: $env:API_BASE_URL" -ForegroundColor Cyan
Write-Host "==> 用例范围: $TestPath" -ForegroundColor Cyan

# ---------- 第四步：执行用例，生成 JSON 数据 ----------
Write-Host "`n==> [第四步] pytest --alluredir=./report 生成 JSON 结果 ..." -ForegroundColor Yellow
pytest $TestPath -v --alluredir=./report --clean-alluredir
$pytestExit = $LASTEXITCODE   # 有用例失败也继续出报告，报告本身就是用来看失败的

# ---------- 第五步：JSON -> HTML ----------
Write-Host "`n==> [第五步] allure generate ./report -o ./html --clean 生成 HTML 报告 ..." -ForegroundColor Yellow
allure generate ./report -o ./html --clean
if ($LASTEXITCODE -ne 0) {
    Write-Host "allure 命令不可用？请先安装：npm install -g allure-commandline（或 scoop install allure）" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`n==> 报告已生成: $RepoRoot\html\index.html" -ForegroundColor Green
Write-Host "    浏览器查看: allure open ./html （或直接双击 html\index.html）" -ForegroundColor Green
Write-Host "    注意：报告含动态资源，需经 HTTP 服务打开（allure open / allure serve），" -ForegroundColor DarkGray
Write-Host "         直接 file:// 双击打开可能白屏。" -ForegroundColor DarkGray

if ($Open) { allure open ./html }
exit $pytestExit
