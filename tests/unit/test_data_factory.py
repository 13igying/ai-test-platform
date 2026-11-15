"""数据工厂的离线单元测试（不发网络请求，只验证数据构造约定）。"""
from __future__ import annotations

from framework.data_factory.user_factory import unique_password, unique_username
from framework.data_factory.video_factory import make_video_payload


def test_unique_username_is_unique_and_prefixed():
    names = {unique_username("t") for _ in range(200)}
    assert len(names) == 200
    assert all(n.startswith("t_") for n in names)


def test_unique_password_format():
    pwd = unique_password()
    assert pwd.startswith("Test#")
    assert len(pwd) == len("Test#") + 8


def test_make_video_payload_fields():
    p1, p2 = make_video_payload(), make_video_payload()
    for p in (p1, p2):
        assert set(p) == {"title", "description", "play_url", "cover_url"}
        assert p["title"].startswith("自动化测试视频_")
        assert p["play_url"].endswith(".mp4")
    # 每次造数必须不同（uuid 后缀），避免并发冲突与限流
    assert p1["title"] != p2["title"]
    assert p1["play_url"] != p2["play_url"]
