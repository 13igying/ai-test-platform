"""AI 失败分诊模块（对应《改进方案》5.4）。

流水线：collector（junit + 证据配对）→ classifier（规则分类）
→ analyzer（LLM 深度分析，offline 时 rules_only）→ 报告（JSON + Markdown）。

原则：
- 分类先行：规则便宜、稳定、可解释；LLM 只处理灰色地带；
- LLM 输入必须先脱敏（密码/token 永远不进模型）；
- 结论分级：defect_candidate 只是"疑似缺陷"，必须人工确认后才上报；
- 证据不足时明确声明 missing_info，而不是让模型编造结论。
"""
