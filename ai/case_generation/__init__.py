"""AI 用例生成模块（对应《改进方案》4.1）。

流水线：LLM 生成候选（或 offline 确定性模板）→ 结构校验（Pydantic）
→ 业务规则校验（白名单 + business_rules/*.yaml）→ 去重 → 评估报告
→ 人工评审 promote → 进 tests/api/test_ai_generated_feed.py 执行。

模块地图：
- schema.py     GeneratedCase Pydantic 模型 + ValidationResult；
- gateway.py    LLM 网关（OpenAI 兼容 /chat/completions），未配置 Key 自动 offline；
- generator.py  offline 确定性生成器 + LLM 生成器（prompt 组装）；
- validator.py  结构 + 业务规则校验 + 签名去重；
- registry.py   业务动作白名单（生成物只能引用这里的 step/assertion）与执行器；
- evaluator.py  生成质量评估（结构有效率 / 业务有效率 / 去重率 / 覆盖增量）；
- cli.py        generate / validate / promote / metrics / demo 五个子命令。
"""
