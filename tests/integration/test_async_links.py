"""跨服务异步链路测试（integration 标记）：点赞/关注/评论经 RabbitMQ 异步落库。

核心方法论（对应《改进方案》3.3 / RESUME 亮点 2）：
HTTP 200 ≠ 业务完成 —— like/comment/follow 的写请求进 MQ，消费者异步
更新 MySQL 与 Redis。断言业务状态必须用 framework.assertions.eventual
的 wait_for 轮询（monotonic 超时 + 轮询期异常容忍 + 最后观测值进超时信息），
并把 APIError（契约破坏，确定性错误）配成 stop_on 立即终止，
与"时序未到"（可继续等）严格区分。

数据策略：module 级复用 author/actor 两个用户（注册限流 5次/小时/IP），
视频每条用例独立发布（uuid 标题，可重复执行）。
"""
from __future__ import annotations

import pytest

from framework.assertions.eventual import wait_for
from framework.clients import APIError, SystemClient
from framework.data_factory import User, publish_video, register_and_login

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def actor(api_base_url) -> User:
    """互动方用户（module 级复用，缓解注册限流）。"""
    return register_and_login(api_base_url, prefix="intactor")


def _vid(video: dict) -> int:
    vid = video.get("video_id") or video.get("id")
    assert vid, f"发布响应缺少视频 id: {video}"
    return int(vid)


def _as_list(data) -> list:
    """评论列表响应兼容裸数组/包装对象两种历史形态。"""
    if isinstance(data, list):
        return data
    return data.get("comments") or data.get("comment_list") or []


def test_like_unlike_eventually_reflected(
    api_base_url, module_user: User, actor: User
):
    """点赞 → 详情 likes_count 最终 = 1（MQ 异步落库）→ 取消 → 回落 0。"""
    vid = _vid(publish_video(api_base_url, module_user))

    actor.client.social.like(vid)
    wait_for(
        lambda: actor.client.video.detail(vid).get("likes_count") == 1,
        timeout=20,
        interval=0.5,
        desc=f"视频 {vid} 点赞数落库为 1",
        stop_on=(APIError,),  # 详情契约破坏是确定性错误，不等
    )

    actor.client.social.unlike(vid)
    wait_for(
        lambda: actor.client.video.detail(vid).get("likes_count") == 0,
        timeout=20,
        interval=0.5,
        desc=f"视频 {vid} 取消点赞后计数回落 0",
        stop_on=(APIError,),
    )


def test_follow_makes_author_appear_in_following_feed(
    api_base_url, module_user: User, actor: User
):
    """关注作者 → 关注流（/feed/listByFollowing，游标单位=秒）最终出现其新视频。"""
    author_id = module_user.account_id
    assert author_id, "工厂未返回 author account_id"
    vid = _vid(publish_video(api_base_url, module_user))

    actor.client.social.follow(author_id)

    def _vlogger_count():
        counts = actor.client.social.counts()
        return counts.get("vlogger_count", 0)

    wait_for(
        lambda: _vlogger_count() >= 1,
        timeout=20,
        interval=0.5,
        desc="关注关系落库（vlogger_count >= 1）",
        stop_on=(APIError,),
    )

    def _video_in_following_feed() -> bool:
        feed = actor.client.feed.by_following(limit=20)
        return any(v["id"] == vid for v in feed.get("video_list", []))

    wait_for(
        _video_in_following_feed,
        timeout=25,
        interval=0.5,
        desc=f"新视频 {vid} 进入关注流（timeline 异步链路）",
        stop_on=(APIError,),
    )


def test_comment_eventually_listed(api_base_url, module_user: User, actor: User):
    """评论发布 → /comment/listAll 最终可见（MQ 异步落库）。"""
    vid = _vid(publish_video(api_base_url, module_user))
    content = f"自动化评论_{vid}"

    actor.client.social.publish_comment(vid, content)

    def _comment_visible() -> bool:
        comments = _as_list(actor.client.social.list_comments(vid))
        return any(c.get("content") == content for c in comments)

    wait_for(
        _comment_visible,
        timeout=20,
        interval=0.5,
        desc=f"评论出现在视频 {vid} 的评论列表",
        stop_on=(APIError,),
    )
