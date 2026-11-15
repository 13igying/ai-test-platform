"""Feed 域端点封装（对齐 backend/internal/feed/handler.go）。

游标口径差异（写用例时最容易踩的坑，面试可讲）：
- listLatest 的 latest_time 是**毫秒**时间戳（handler 用 time.UnixMilli）；
- listByFollowing 的 latest_time 是**秒**时间戳（handler 用 time.Unix）；
- listLikesCount 游标必须成对出现（likes_count_before + id_before），
  且 id_before=0 时 likes_count_before 也必须为 0；
- limit 合法域 1..50，越界不报错而是重置为 10——这是"宽容降级"契约，
  测试应断言"重置为 10"而不是断言 400。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.clients.base_client import BaseClient


class FeedAPI:
    """最新流 / 热度流 / 关注流 / 标签流 / 热度榜。"""

    def __init__(self, base: "BaseClient") -> None:
        self._b = base

    def _c(self):
        return self._b if getattr(self, "_b", None) is not None else self

    # ---------- 端点 ----------
    def latest(self, limit: int = 10, latest_time: int = 0) -> dict:
        """最新流（latest_time 为毫秒时间戳游标）。"""
        return self._c().post_ok(
            "/feed/listLatest", {"limit": limit, "latest_time": latest_time}, schema="feed"
        )

    def by_likes(self, limit: int = 10, likes_count_before: int = 0, id_before: int = 0) -> dict:
        """按点赞数排序（复合游标：likes_count_before + id_before 成对出现）。"""
        return self._c().post_ok(
            "/feed/listLikesCount",
            {
                "limit": limit,
                "likes_count_before": likes_count_before,
                "id_before": id_before,
            },
            schema="feed",
        )

    def by_following(self, limit: int = 10, latest_time: int = 0) -> dict:
        """关注流（硬认证；latest_time 为秒级时间戳——与 listLatest 口径不同）。"""
        return self._c().post_ok(
            "/feed/listByFollowing", {"limit": limit, "latest_time": latest_time}, schema="feed"
        )

    def by_tag(self, tag_name: str, limit: int = 10) -> dict:
        """按标签检索（响应仅 {video_list}，无游标字段）。"""
        return self._c().post_ok("/feed/listByTag", {"tag_name": tag_name, "limit": limit})

    def by_popularity(
        self,
        limit: int = 10,
        latest_popularity: int = 0,
        latest_before: str = "",
        latest_id_before: int = 0,
        as_of: int = 0,
        offset: int = 0,
    ) -> dict:
        """热度榜（复合游标：latest_before + latest_id_before 成对出现）。"""
        body: dict[str, Any] = {"limit": limit, "offset": offset}
        if latest_popularity:
            body["latest_popularity"] = latest_popularity
        if latest_before:
            body["latest_before"] = latest_before
        if latest_id_before:
            body["latest_id_before"] = latest_id_before
        if as_of:
            body["as_of"] = as_of
        return self._c().post_ok("/feed/listByPopularity", body)

    # ---------- v1 兼容平铺名 ----------
    def feed_latest(self, limit: int = 10, latest_time: int = 0) -> dict:
        return self.latest(limit=limit, latest_time=latest_time)

    def feed_by_likes(self, limit: int = 10, likes_count_before: int = 0, id_before: int = 0) -> dict:
        return self.by_likes(limit=limit, likes_count_before=likes_count_before, id_before=id_before)

    def feed_by_following(self, limit: int = 10, latest_time: int = 0) -> dict:
        return self.by_following(limit=limit, latest_time=latest_time)
