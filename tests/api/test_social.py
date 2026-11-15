"""社交互动测试：点赞 / 关注 / 评论。

注意：like/comment/follow 走 MQ 异步落库，断言前用 wait_until 轮询。
核心链路响应带 jsonschema 结构契约校验（schema="..."，契约定义见 utils/schemas.py）。
响应结构（对齐后端 handler）：
- /like/listMyLikedVideos -> 裸数组 [{video...}]
- /comment/listAll        -> 裸数组 [{comment...}]
- /social/getAllFollowers -> {followers: [...], follower_count: n}
- /social/getCounts       -> {follower_count, vlogger_count}（基于 JWT，无参数）
"""
import pytest

from tests.api.utils.allure_ext import allure
from tests.api.utils.client import APIClient
from tests.api.utils.factories import publish_video, wait_until

pytestmark = pytest.mark.api


@allure.feature("社交互动模块")
@allure.story("点赞")
class TestLike:
    @allure.severity("blocker")
    def test_like_unlike_cycle(self, api_base_url, module_user):
        """点赞 -> isLiked=true -> 取消 -> isLiked=false。"""
        video = publish_video(api_base_url, module_user)
        vid = video.get("id") or video.get("video_id")

        with allure.step("第一步：点赞"):
            module_user.client.like(vid)

        def _liked():
            return module_user.client.is_liked(vid).get("is_liked") is True

        wait_until(_liked, timeout=10, desc="isLiked 变为 true（MQ 异步）")

        with allure.step("第二步：取消点赞"):
            module_user.client.unlike(vid)

        def _unliked():
            return module_user.client.is_liked(vid).get("is_liked") is False

        wait_until(_unliked, timeout=10, desc="isLiked 变为 false（MQ 异步）")

    @allure.severity("critical")
    def test_likes_count_increases(self, api_base_url, module_user, user):
        """A 点赞 B 的视频，B 视频点赞数 +1（MQ 异步 + getDetail 有 Redis 缓存）。

        注意：先点赞、再首次读详情。若在点赞前先读一次 getDetail，
        cache-aside 会把旧值 0 回填进 Redis，之后轮询一直命中缓存的 0，
        直到 TTL 过期才能看到新值——读的顺序会直接决定用例成败。
        """
        video = publish_video(api_base_url, module_user)
        vid = video.get("id") or video.get("video_id")

        user.client.like(vid)

        def _increased():
            return module_user.client.likes_count(vid) >= 1

        wait_until(_increased, timeout=15, desc="点赞数增加（MQ 异步 + 缓存回填）")

    @allure.severity("critical")
    def test_my_liked_list(self, api_base_url, module_user, user):
        """点赞后出现在我的喜欢列表（响应为裸数组）。"""
        video = publish_video(api_base_url, module_user)
        vid = video.get("id") or video.get("video_id")
        user.client.like(vid)

        def _in_list():
            videos = user.client.list_my_liked(limit=20)
            return any(v.get("id") == vid for v in videos)

        wait_until(_in_list, timeout=10, desc="视频进入我的喜欢列表（MQ 异步）")


@allure.feature("社交互动模块")
@allure.story("关注")
class TestFollow:
    @allure.severity("blocker")
    def test_follow_unfollow_cycle(self, api_base_url, module_user, user):
        """关注 -> 粉丝列表包含 -> 取关 -> 不包含。"""
        module_user.client.follow(user.account_id)

        def _followed():
            followers = user.client.post_ok(
                "/social/getAllFollowers", {}, schema="followers"
            )
            fl = followers.get("followers") or []
            return any(f.get("id") == module_user.account_id for f in fl)

        wait_until(_followed, timeout=10, desc="粉丝列表包含关注者（MQ 异步）")

        module_user.client.unfollow(user.account_id)

        def _unfollowed():
            followers = user.client.post_ok(
                "/social/getAllFollowers", {}, schema="followers"
            )
            fl = followers.get("followers") or []
            return not any(f.get("id") == module_user.account_id for f in fl)

        wait_until(_unfollowed, timeout=10, desc="取关后粉丝列表移除（MQ 异步）")

    @allure.severity("critical")
    def test_get_counts(self, api_base_url, module_user, user):
        """getCounts 基于 JWT 返回粉丝/关注计数（无请求参数）。"""
        module_user.client.follow(user.account_id)

        def _count_visible():
            data = user.client.post_ok("/social/getCounts", {}, schema="social_counts")
            return int(data.get("follower_count", 0)) >= 1

        wait_until(_count_visible, timeout=10, desc="follower_count >= 1（MQ 异步）")

        data = module_user.client.post_ok("/social/getCounts", {}, schema="social_counts")
        assert "follower_count" in data and "vlogger_count" in data


@allure.feature("社交互动模块")
@allure.story("评论")
class TestComment:
    @allure.severity("critical")
    def test_publish_and_list(self, api_base_url, module_user, user):
        """发评论 -> 评论列表可见（listAll 返回裸数组）。"""
        video = publish_video(api_base_url, module_user)
        vid = video.get("id") or video.get("video_id")
        content = f"自动化评论_{id(user)}"
        user.client.publish_comment(vid, content)

        def _visible():
            comments = module_user.client.list_comments(vid)
            if isinstance(comments, dict):
                comments = comments.get("comment_list") or []
            return any(content in (c.get("content", "")) for c in comments)

        wait_until(_visible, timeout=10, desc="评论出现在列表（MQ 异步）")

    @allure.severity("blocker")
    def test_comment_requires_auth(self, anon_client: APIClient):
        """未登录发评论应 401。"""
        anon_client.post_expect_error("/comment/publish", {"video_id": 1, "content": "x"}, 401)
