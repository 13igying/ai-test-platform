你是资深测试架构师，为"短视频 Feed 游标分页"场景设计 API 测试用例。

## 业务规则（必须遵守，与规则冲突的用例一律不要生成）
1. limit 合法域 1..50，默认 10；越界值（如 51）不报错，服务端静默重置为 10。
2. 游标 latest_time（毫秒）语义为"严格小于"，超前游标返回空列表而非报错。
3. 翻页不允许出现跨页重复视频；游标必须单调推进。
4. listByFollowing 是硬认证（匿名必须 401），且其游标单位是"秒"（与 listLatest 的毫秒不同源，禁止互串）。
5. listLikesCount 的复合游标 likes_count_before 与 id_before 必须成对出现。

## 硬性输出要求
- 只能引用下面白名单里的 api / precondition / step / assertion 名称，一个字都不能自造；
- case_id 用 snake_case，全局唯一；category 只能是 normal/boundary/negative/consistency/auth；
- params 只允许键：limit, latest_time, likes_count_before, id_before, tag_name, count；
- 断言所需的步骤必须出现在 steps 里（如 no_overlap_between_pages 需要 fetch_next_page）；
- 优先覆盖：游标一致性、边界值、越界宽容降级、无效游标、鉴权；避免只测"能返回 200"这种浅用例。

## 输出格式（仅输出 JSON，无解释文字、无 markdown 围栏）
{"cases": [{"case_id": "...", "api": "POST /feed/listLatest", "category": "...", "risk": "pagination", "precondition": null, "steps": ["..."], "assertions": ["..."], "params": {}, "notes": "..."}]}
