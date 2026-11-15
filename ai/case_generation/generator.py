"""用例生成器：offline 确定性模板 + LLM 生成（两条路径同一份校验出口）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ai.case_generation.gateway import GatewayError, LLMGateway, OfflineModeError
from ai.case_generation.registry import ASSERTIONS, PRECONDITIONS, STEPS

PROMPTS_DIR = Path(__file__).parent / "prompts"


# ---------------------------------------------------------------------------
# offline 确定性生成（无 LLM 时的基线，也是评估 LLM 产出的"覆盖率下界"）
# ---------------------------------------------------------------------------

def offline_feed_cursor_cases() -> list[dict[str, Any]]:
    """feed 游标分页场景的确定性用例集（覆盖 normal/boundary/negative/consistency/auth）。"""
    base = "POST /feed/listLatest"
    cases: list[dict[str, Any]] = [
        {
            "case_id": "feed_latest_first_page_normal",
            "api": base,
            "category": "normal",
            "risk": "pagination",
            "steps": ["fetch_first_page"],
            "assertions": ["page_size_respected", "video_id_unique"],
            "params": {"limit": 10},
            "notes": "首屏默认 limit 正常返回",
            "source": "offline",
        },
        {
            "case_id": "feed_latest_cursor_pagination_consistency",
            "api": base,
            "category": "consistency",
            "risk": "pagination",
            "precondition": "seed_video_dataset",
            "steps": ["fetch_first_page", "fetch_next_page"],
            "assertions": [
                "cursor_progresses",
                "no_overlap_between_pages",
                "page_size_respected",
            ],
            "params": {"limit": 2, "count": 3},
            "notes": "游标翻页不重复、游标单调推进",
            "source": "offline",
        },
        {
            "case_id": "feed_latest_limit_min_boundary",
            "api": base,
            "category": "boundary",
            "risk": "pagination",
            "steps": ["fetch_first_page"],
            "assertions": ["page_size_respected"],
            "params": {"limit": 1},
            "notes": "合法域下界 limit=1",
            "source": "offline",
        },
        {
            "case_id": "feed_latest_limit_max_boundary",
            "api": base,
            "category": "boundary",
            "risk": "pagination",
            "steps": ["fetch_first_page"],
            "assertions": ["page_size_respected"],
            "params": {"limit": 50},
            "notes": "合法域上界 limit=50",
            "source": "offline",
        },
        {
            "case_id": "feed_latest_limit_out_of_domain_reset",
            "api": base,
            "category": "boundary",
            "risk": "pagination",
            "steps": ["fetch_boundary_limit"],
            "assertions": ["out_of_domain_limit_reset_to_default"],
            "params": {"limit": 51},
            "notes": "越界 limit=51 按契约重置为 10（宽容降级）",
            "source": "offline",
        },
        {
            "case_id": "feed_latest_future_cursor_empty_page",
            "api": base,
            "category": "negative",
            "risk": "pagination",
            "steps": ["fetch_with_invalid_cursor"],
            "assertions": ["future_cursor_empty_page"],
            "params": {"latest_time": 253402185600000},
            "notes": "超前游标（10000 年）返回空列表而非报错",
            "source": "offline",
        },
        {
            "case_id": "feed_following_requires_auth",
            "api": "POST /feed/listByFollowing",
            "category": "auth",
            "risk": "auth",
            "steps": ["fetch_following_feed_anonymous"],
            "assertions": ["unauthenticated_rejected_401"],
            "params": {"limit": 5},
            "notes": "关注流硬认证：匿名访问必须 401",
            "source": "offline",
        },
        {
            "case_id": "feed_following_authed_contract",
            "api": "POST /feed/listByFollowing",
            "category": "normal",
            "risk": "auth",
            "steps": ["fetch_following_feed_authed"],
            "assertions": ["following_feed_contract"],
            "params": {"limit": 10},
            "notes": "已登录关注流响应契约",
            "source": "offline",
        },
    ]
    return cases


# ---------------------------------------------------------------------------
# LLM 生成（prompt = 模板 + 白名单动态注入，保证 prompt 永不与代码漂移）
# ---------------------------------------------------------------------------

def build_prompt(scenario: str, count: int) -> tuple[str, str]:
    """返回 (system_prompt, user_prompt)。"""
    system = (PROMPTS_DIR / f"{scenario}_v1.md").read_text(encoding="utf-8")
    whitelist = (
        "可选 API：POST /feed/listLatest, POST /feed/listLikesCount, "
        "POST /feed/listByFollowing, POST /feed/listByTag\n"
        f"可选 precondition：{', '.join(sorted(PRECONDITIONS))}\n"
        f"可选 step：{', '.join(sorted(STEPS))}\n"
        f"可选 assertion：{', '.join(sorted(ASSERTIONS))}\n"
    )
    user = (
        f"请为 feed 游标分页场景生成 {count} 条互不重复的测试用例。\n"
        f"{whitelist}\n"
        '严格输出 JSON：{"cases": [ GeneratedCase... ]}，不要输出任何解释文字。'
    )
    return system, user


def llm_feed_cursor_cases(gateway: LLMGateway, count: int = 6) -> list[dict[str, Any]]:
    """走 LLM 生成候选；offline/网关异常向上抛，由 CLI 决定是否降级。"""
    system, user = build_prompt("feed_cursor", count)
    data = gateway.chat_json(system, user, temperature=0.3)
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list):
        raise GatewayError(f"LLM 输出缺少 cases 数组: {data!r:.300}")
    for c in cases:
        if isinstance(c, dict):
            c.setdefault("source", "llm")
    return cases


__all__ = [
    "offline_feed_cursor_cases",
    "llm_feed_cursor_cases",
    "build_prompt",
    "OfflineModeError",
]
