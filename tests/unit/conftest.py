"""单元测试层 conftest：不依赖后端（离线），不注册任何环境门禁。

覆盖对象：framework/*（eventual、redact、evidence、base_client）与
ai/*（case_generation、failure_triage）。这层是 CI 里的"offline 单测 job"，
保证框架与 AI 平台逻辑在无后端环境即可验证。
"""
