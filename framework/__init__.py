"""统一测试框架层（video-quality 平台的工程底座）。

分层职责（对应《改进方案》2.1 架构原则）：
- clients/       统一 API Client 层：base_url/鉴权/超时/request_id/日志/证据
- data_factory/  测试数据工厂：用户、视频、社交关系
- assertions/    断言组件：最终一致性等待（eventual）与响应结构契约（schema）
- observability/ 观测能力：失败证据采集、脱敏、Allure 装饰、pytest 插件
- fixtures/      可复用夹具实现（pytest fixture 在 tests/*/conftest.py 中包装）
- config.py      环境配置中枢（全部来自环境变量，12-factor 风格）

导入约定：业务测试一律 `from framework.xxx import ...`，
tests/api/utils/ 下的旧路径仅为兼容 shim，新代码禁止引用。
"""
