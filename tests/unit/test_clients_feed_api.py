"""客户端封装的离线单元测试（FakeBase 桩掉 HTTP，验证路径/游标/契约映射）。"""
from __future__ import annotations

import json

import httpx
import pytest

from framework.clients import SystemClient
from framework.clients.feed_api import FeedAPI


class FakeBase:
    """记录 post_ok 调用的桩（BaseClient 的鸭子类型替身）。"""

    def __init__(self, canned: dict | None = None):
        self.calls: list[tuple[str, dict, str | None]] = []
        self._canned = canned or {"video_list": [], "has_more": False, "next_time": 0}

    def post_ok(self, path: str, body: dict | None = None, schema: str | None = None) -> dict:
        self.calls.append((path, body or {}, schema))
        return self._canned

    def post_expect_error(self, path: str, body: dict | None, expect_status) -> dict:
        self.calls.append((path, body or {}, None))
        return {"status": expect_status}


def test_feed_latest_maps_path_and_params():
    base = FakeBase()
    resp = FeedAPI(base).latest(limit=7, latest_time=123)
    assert base.calls == [("/feed/listLatest", {"limit": 7, "latest_time": 123}, "feed")]
    assert resp["has_more"] is False


def test_feed_likes_count_cursor_pair_always_sent():
    """复合游标必须成对出现（id_before=0 时 likes_count_before 也为 0）。"""
    base = FakeBase()
    FeedAPI(base).by_likes(limit=3)
    path, body, schema = base.calls[0]
    assert path == "/feed/listLikesCount"
    assert body["likes_count_before"] == 0 and body["id_before"] == 0
    FeedAPI(base).by_likes(limit=3, likes_count_before=12, id_before=45)
    assert base.calls[1][1] == {"limit": 3, "likes_count_before": 12, "id_before": 45}


def test_feed_by_following_default_limit():
    base = FakeBase()
    FeedAPI(base).by_following()
    path, body, _ = base.calls[0]
    assert path == "/feed/listByFollowing"
    assert body == {"limit": 10, "latest_time": 0}


def test_feed_by_tag_sends_tag_name():
    base = FakeBase()
    FeedAPI(base).by_tag("旅行")
    path, body, _ = base.calls[0]
    assert path == "/feed/listByTag"
    assert body["tag_name"] == "旅行"


def test_system_client_flat_compat_and_subclients():
    """平铺兼容方法（v1 迁移期）与子客户端视图必须同时可用。"""
    c = SystemClient("http://mock.local")
    try:
        for name in ("feed_latest", "feed_by_likes", "feed_by_following"):
            assert hasattr(c, name), f"SystemClient 缺少兼容平铺名 {name}"
        assert isinstance(c.feed, FeedAPI)
        assert c.account is not None and c.video is not None
    finally:
        c.close()


def _mock_client(handler) -> SystemClient:
    """真实 SystemClient + MockTransport：不碰网络，走完整请求管线。"""
    c = SystemClient("http://mock.local")
    c._http = httpx.Client(base_url="http://mock.local", transport=httpx.MockTransport(handler))
    return c


def test_system_client_feed_latest_full_pipeline():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["request_id"] = request.headers.get("X-Request-Id")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200, json={"code": 0, "video_list": [], "has_more": False, "next_time": 0}
        )

    c = _mock_client(handler)
    try:
        resp = c.feed.latest(limit=3)
        assert resp["has_more"] is False
        assert captured["path"] == "/feed/listLatest"
        assert captured["body"]["limit"] == 3
        assert captured["request_id"]  # 每个请求都带测试侧 request_id

        flat = c.feed_latest(limit=3)  # 平铺兼容名等价于子客户端调用
        assert flat == resp
    finally:
        c.close()


def test_system_client_post_expect_error_tuple():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 401, "msg": "unauthorized"})

    c = _mock_client(handler)
    try:
        out = c.post_expect_error("/feed/listByFollowing", {"limit": 1}, (401, 403))
        assert out["code"] == 401
    finally:
        c.close()


def test_system_client_unexpected_status_raises_apierror():
    from framework.clients import APIError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    c = _mock_client(handler)
    try:
        with pytest.raises(APIError) as exc:
            c.post_ok("/feed/listLatest", {"limit": 1})
        assert "500" in str(exc.value)
    finally:
        c.close()
