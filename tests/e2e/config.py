"""UI 自动化配置：视口、超时、测试账号约定、截图目录。

集中管理"环境差异"和"证据输出位置"，页面对象与用例只 import 这里的常量，
调整分辨率/超时只改这一个文件。
"""
from tests.e2e.pages.base_page import SHOTS_DIR

# 浏览器视口：与产品主流用户分辨率对齐
VIEWPORT = {"width": 1280, "height": 800}

# Playwright 元素等待超时（毫秒）：禁止 sleep，统一走自动等待 + 该兜底
DEFAULT_TIMEOUT_MS = 10_000

# UI 测试专用密码约定（用户名按用例随机生成）
UI_PASSWORD = "Passw0rd!123"

# E2E 用例的截图目录（ui_shots 的子目录，Web 运行器截图墙只读平铺层，互不干扰）
E2E_SHOTS = SHOTS_DIR / "e2e"
