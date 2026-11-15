"""业务动作白名单与执行器（改进方案 4.1 第二层的"执行侧"）。

设计要点：
- 生成物（LLM/offline）只能引用这里登记的 precondition/step/assertion 名——
  白名单既约束生成，也是执行的唯一入口，"生成什么"与"能执行什么"天然一致；
- 执行器 run_case 是场景无关的最小编排器：precondition → steps → assertions，
  每步记录到 ctx.state，断言失败抛 AssertionError（pytest 原生判失败）；
- client 从 ctx 注入（不在这里构造）：单测用 FakeClient 验证编排逻辑，
  联调/回归用 SystemClient 打真实后端——同一份 registry 两种跑法。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from framework.observability.allure_ext import allure

# ---------------------------------------------------------------------------
# 白名单登记处：新增业务动作 = 在对应字典加一个函数，prompt 自动带上
# ---------------------------------------------------------------------------

PRECONDITIONS: dict[str, Callable[..., Any]] = {}
STEPS: dict[str, Callable[..., Any]] = {}
ASSERTIONS: dict[str, Callable[..., Any]] = {}


def precondition(fn):
    PRECONDITIONS[fn.__name__] = fn
    return fn


def step(fn):
    STEPS[fn.__name__] = fn
    return fn


def assertion(fn):
    ASSERTIONS[fn.__name__] = fn
    return fn


@dataclass
class CaseContext:
    """一次用例执行的上下文（client 注入，业务数据进 state）。"""

    base_url: str
    client: Any                      # 主 client（已认证或匿名，由场景决定）
    anon_client: Any = None          # 匿名 client（auth 类场景用）
    author: Any = None               # 造数用作者（User 对象或鸭子类型）
    state: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 前置数据动作
# ---------------------------------------------------------------------------

@precondition
def seed_video_dataset(ctx: CaseContext, count: int = 3, **_) -> None:
    """作者发布 count 个视频（间隔 >1s 保证 create_time 单调，见 video_factory）。"""
    from framework.data_factory.video_factory import publish_videos

    if ctx.author is None:
        raise RuntimeError("seed_video_dataset 需要 ctx.author（测试用户）")
    payloads = publish_videos(ctx.base_url, ctx.author, count=count)
    ctx.state["seeded_ids"] = [p.get("id") or p.get("video_id") for p in payloads]


# ---------------------------------------------------------------------------
# 执行步骤
# ---------------------------------------------------------------------------

@step
def fetch_first_page(ctx: CaseContext, limit: int = 10, **_) -> None:
    ctx.state["page1"] = ctx.client.feed.latest(limit=limit)


@step
def fetch_next_page(ctx: CaseContext, limit: int = 10, **_) -> None:
    """用第一页 next_time 游标翻第二页（listLatest 游标单位：毫秒）。"""
    page1 = ctx.state.get("page1")
    if page1 is None:
        raise RuntimeError("fetch_next_page 依赖 fetch_first_page 先执行")
    ctx.state["page2"] = ctx.client.feed.latest(limit=limit, latest_time=page1["next_time"])


@step
def fetch_last_page(ctx: CaseContext, limit: int = 10, max_pages: int = 10, **_) -> None:
    """沿游标翻到 has_more=False 为止（防死循环：最多 max_pages 页）。"""
    pages = [ctx.state.get("page1") or ctx.client.feed.latest(limit=limit)]
    for _ in range(max_pages - 1):
        last = pages[-1]
        if not last["has_more"]:
            break
        pages.append(ctx.client.feed.latest(limit=limit, latest_time=last["next_time"]))
    ctx.state["pages"] = pages


@step
def fetch_with_invalid_cursor(ctx: CaseContext, latest_time: int = 253402185600000, **_) -> None:
    """超前游标（默认 10000 年，毫秒）：业务规则为返回空列表而非报错。"""
    ctx.state["invalid_cursor_page"] = ctx.client.feed.latest(latest_time=latest_time)


@step
def fetch_boundary_limit(ctx: CaseContext, limit: int = 51, **_) -> None:
    """越界 limit（默认 51，超出合法域 1..50）：业务规则为重置为 10 而非报错。"""
    ctx.state["boundary_page"] = ctx.client.feed.latest(limit=limit)


@step
def fetch_following_feed_anonymous(ctx: CaseContext, limit: int = 5, **_) -> None:
    """匿名请求关注流（硬认证）：预期 401，post_expect_error 记录状态码。"""
    resp = ctx.anon_client.post_expect_error("/feed/listByFollowing", {"limit": limit}, 401)
    ctx.state["following_anon_status"] = 401
    ctx.state["following_anon_resp"] = resp



# ---------------------------------------------------------------------------
# 断言
# ---------------------------------------------------------------------------

@assertion
def page_size_respected(ctx: CaseContext, limit: int = 10, page_key: str = "page1", **_) -> None:
    page = ctx.state.get(page_key)
    assert page is not None, f"缺少页面数据 state[{page_key!r}]（步骤未执行？）"
    assert len(page["video_list"]) <= limit, (
        f"[分页] limit={limit} 但返回 {len(page['video_list'])} 条"
    )


@assertion
def video_id_unique(ctx: CaseContext, **_) -> None:
    page = ctx.state.get("page1")
    ids = [v["id"] for v in page["video_list"]]
    assert len(ids) == len(set(ids)), f"[分页] 单页内出现重复视频 id: {ids}"


@assertion
def cursor_progresses(ctx: CaseContext, **_) -> None:
    """第一页 has_more=True 时游标必须有效（>0），第二页必须存在。"""
    page1, page2 = ctx.state["page1"], ctx.state.get("page2")
    if page1["has_more"]:
        assert page1["next_time"] > 0, "[分页] has_more=True 但游标 next_time 为空"
        assert page2 is not None, "[分页] 未执行 fetch_next_page"


@assertion
def no_overlap_between_pages(ctx: CaseContext, **_) -> None:
    ids1 = {v["id"] for v in ctx.state["page1"]["video_list"]}
    ids2 = {v["id"] for v in ctx.state["page2"]["video_list"]}
    assert ids1.isdisjoint(ids2), f"[分页] 翻页出现重复: {ids1 & ids2}"


@assertion
def out_of_domain_limit_reset_to_default(ctx: CaseContext, **_) -> None:
    """业务规则：越界 limit 不报错，重置为默认 10（宽容降级契约）。"""
    page = ctx.state["boundary_page"]
    assert len(page["video_list"]) <= 10, (
        f"[分页] 越界 limit 未按契约重置为 10：返回 {len(page['video_list'])} 条"
    )


@assertion
def future_cursor_empty_page(ctx: CaseContext, **_) -> None:
    """业务规则：超前游标返回空列表（不是 4xx/5xx，也不是残留数据）。"""
    page = ctx.state["invalid_cursor_page"]
    assert page["video_list"] == [], (
        f"[分页] 超前游标应返回空列表，实际 {len(page['video_list'])} 条"
    )


@assertion
def unauthenticated_rejected_401(ctx: CaseContext, **_) -> None:
    assert ctx.state.get("following_anon_status") == 401, (
        f"[鉴权] 匿名访问关注流未被 401 拒绝: {ctx.state.get('following_anon_status')}"
    )


@assertion
def following_feed_contract(ctx: CaseContext, **_) -> None:
    """关注流响应契约：video_list/has_more 字段在（schema 校验已在 client 层做过）。"""
    page = ctx.state.get("following_authed")
    assert page is not None, "未执行 fetch_following_feed_authed"
    assert isinstance(page["video_list"], list)


# ---------------------------------------------------------------------------
# 执行器
# ---------------------------------------------------------------------------

def run_case(case, ctx: CaseContext) -> dict:
    """执行一条 GeneratedCase：precondition → steps → assertions。

    返回执行轨迹（供 AI 生成用例的运行报告）；断言失败向上抛
    AssertionError，由 pytest 记录为用例失败——生成用例与手写用例
    的失败处理完全同构。
    """
    trace: dict[str, Any] = {"case_id": case.case_id, "api": case.api, "executed": []}
    with allure.step(f"AI 生成用例执行：{case.case_id}（{case.category}）"):
        if case.precondition:
            fn = PRECONDITIONS[case.precondition]
            fn(ctx, **case.params)
            trace["executed"].append({"kind": "precondition", "name": case.precondition})
        for name in case.steps:
            STEPS[name](ctx, **case.params)
            trace["executed"].append({"kind": "step", "name": name})
        for name in case.assertions:
            with allure.step(f"断言：{name}"):
                ASSERTIONS[name](ctx, **case.params)
            trace["executed"].append({"kind": "assertion", "name": name})
    return trace


@step
def fetch_following_feed_authed(ctx: CaseContext, limit: int = 10, **_) -> None:
    ctx.state["following_authed"] = ctx.client.feed.by_following(limit=limit)
