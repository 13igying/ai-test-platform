"""社交域端点封装（点赞 / 关注 / 评论，对齐 video/like_handler.go、
video/comment_handler.go 与 social/handler.go）。

注意：like/comment/follow 写操作经 RabbitMQ 异步落库——断言业务状态前
必须配合 framework.assertions.eventual.wait_for 轮询（最终一致性）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.clients.base_client import BaseClient


class SocialAPI:
    """点赞 / 关注 / 评论 / 计数。"""

    def __init__(self, base: "BaseClient") -> None:
        self._b = base

    def _c(self):
        return self._b if getattr(self, "_b", None) is not None else self

    # ---------- 点赞 ----------
    def like(self, video_id: int) -> dict:
        return self._c().post_ok("/like/like", {"video_id": video_id})

    def unlike(self, video_id: int) -> dict:
        return self._c().post_ok("/like/unlike", {"video_id": video_id})

    def is_liked(self, video_id: int) -> dict:
        return self._c().post_ok("/like/isLiked", {"video_id": video_id}, schema="is_liked")

    def list_my_liked(self, limit: int = 20) -> list:
        """我的喜欢列表（响应为裸数组）。"""
        data = self._c().post_ok("/like/listMyLikedVideos", {"limit": limit})
        return data if isinstance(data, list) else data.get("video_list", [])

    # ---------- 关注 ----------
    def follow(self, vlogger_id: int) -> dict:
        return self._c().post_ok("/social/follow", {"vlogger_id": vlogger_id})

    def unfollow(self, vlogger_id: int) -> dict:
        return self._c().post_ok("/social/unfollow", {"vlogger_id": vlogger_id})

    def followers(self) -> dict:
        return self._c().post_ok("/social/getAllFollowers", {}, schema="followers")

    def vloggers(self) -> dict:
        return self._c().post_ok("/social/getAllVloggers", {})

    def counts(self) -> dict:
        """基于 JWT 的粉丝/关注计数（无请求参数）。"""
        return self._c().post_ok("/social/getCounts", {}, schema="social_counts")

    # ---------- 评论 ----------
    def publish_comment(self, video_id: int, content: str) -> dict:
        return self._c().post_ok("/comment/publish", {"video_id": video_id, "content": content})

    def list_comments(self, video_id: int) -> list | dict:
        """评论列表（响应为裸数组）。"""
        return self._c().post_ok("/comment/listAll", {"video_id": video_id})

    # ---------- v1 兼容平铺名 ----------
    def likes_count(self, video_id: int) -> int:
        """点赞数（后端无独立接口，从详情取；详情有 Redis 缓存）。"""
        return int(self._c().video.detail(video_id).get("likes_count", 0))
