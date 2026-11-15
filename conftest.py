"""仓库根 conftest：注册全局 pytest 插件。

framework.observability.pytest_plugin 负责：
- 每条用例开始时初始化失败证据容器；
- 失败时把证据落盘 reports/evidence/<case>.json 并挂 Allure 附件。

pytest 要求 pytest_plugins 必须声明在 rootdir 级 conftest（本文件）。
"""
pytest_plugins = ("framework.observability.pytest_plugin",)
