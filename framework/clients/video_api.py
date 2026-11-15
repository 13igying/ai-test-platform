"""视频域端点封装（对齐 backend/internal/video/video_handler.go）。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.clients.base_client import BaseClient


class VideoAPI:
    """发布 / 详情 / 作者列表 / 删除。"""

    def __init__(self, base: "BaseClient") -> None:
        self._b = base

    def _c(self):
        return self._b if getattr(self, "_b", None) is not None else self

    # ---------- 端点 ----------
    def publish(self, **payload: Any) -> dict:
        """发布视频（play_url 方式，无需真实文件），返回含 id 的视频对象。"""
        return self._c().post_ok("/video/publish", payload)

    def detail(self, video_id: int) -> dict:
        """视频详情（含 likes_count；后端走 Redis cache-aside）。"""
        return self._c().post_ok("/video/getDetail", {"id": video_id}, schema="video_detail")

    def list_by_author(self, author_id: int) -> list:
        """作者的视频列表（裸数组）。"""
        data = self._c().post_ok("/video/listByAuthorID", {"author_id": author_id})
        return data if isinstance(data, list) else data.get("videos", [])

    def delete(self, video_id: int) -> dict:
        return self._c().post_ok("/video/delete", {"id": video_id})

    # ---------- v1 兼容平铺名 ----------
    def video_detail(self, video_id: int) -> dict:
        return self.detail(video_id)
