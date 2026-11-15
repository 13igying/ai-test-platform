"""越权/鉴权安全测试（对应 pytest.ini security 标记）。

受保护路由清单直接从 backend/internal/http/router.go 提取（JWTAuth 组），
矩阵化验证：无 token 必须 401。公开路由与软认证路由做正向抽样对照——
防止"把公开接口也锁死"的过矫正。

路由分组（router.go）：
- protectedAccountGroup: /account/{logout,rename,uploadAvatar,updateProfile}
- protectedVideoGroup:   /video/{uploadVideo,uploadCover,publish,chunk/*}
- protectedLikeGroup:    /like/{like,unlike,isLiked,listMyLikedVideos}
- protectedCommentGroup: /comment/{publish,delete}（/comment/listAll 公开）
- protectedSocialGroup:  /social/{follow,unfollow,getAllFollowers,getAllVloggers,getCounts}
- protectedFeedGroup:    /feed/listByFollowing（其余 feed 路由 SoftJWTAuth 匿名可浏览）
- protectedMessageGroup: /message/{send,list}
- protectedBugGroup:     /bug/{create,updateStatus,list}
"""
from __future__ import annotations

import pytest

from framework.clients import SystemClient

pytestmark = pytest.mark.security

# (路由, 最小请求体)——JWT 中间件先于 handler/参数绑定执行，
# 统一断言 401（403 视为等价的"被授权体系拒绝"）
PROTECTED_ROUTES: list[tuple[str, dict]] = [
    ("/account/logout", {}),
    ("/account/rename", {"new_username": "sec_probe"}),
    ("/account/uploadAvatar", {}),
    ("/account/updateProfile", {}),
    ("/video/uploadVideo", {}),
    ("/video/uploadCover", {}),
    ("/video/publish", {}),
    ("/video/chunk/init", {}),
    ("/video/chunk/upload", {}),
    ("/video/chunk/status", {}),
    ("/video/chunk/complete", {}),
    ("/like/like", {"video_id": 1}),
    ("/like/unlike", {"video_id": 1}),
    ("/like/isLiked", {"video_id": 1}),
    ("/like/listMyLikedVideos", {"limit": 1}),
    ("/comment/publish", {"video_id": 1, "content": "sec"}),
    ("/comment/delete", {"id": 1}),
    ("/social/follow", {"vlogger_id": 1}),
    ("/social/unfollow", {"vlogger_id": 1}),
    ("/social/getAllFollowers", {}),
    ("/social/getAllVloggers", {}),
    ("/social/getCounts", {}),
    ("/feed/listByFollowing", {"limit": 1}),
    ("/message/send", {"to": 1, "content": "sec"}),
    ("/message/list", {}),
    ("/bug/create", {}),
    ("/bug/updateStatus", {"id": 1, "status": "open"}),
    ("/bug/list", {}),
]


@pytest.mark.parametrize("path,body", PROTECTED_ROUTES, ids=[p for p, _ in PROTECTED_ROUTES])
def test_protected_route_rejects_anonymous(anon_client: SystemClient, path: str, body: dict):
    """无 token 访问受保护路由 → 401/403，不允许 200/404/500 泄漏。"""
    resp = anon_client.post_expect_error(path, body, (401, 403))
    # 响应体不要求特定结构，但不得把业务数据直接返回
    assert not isinstance(resp, list), f"{path} 匿名访问竟返回了业务列表: {resp}"


def test_forged_token_rejected(api_base_url: str):
    """伪造签名 token 同样必须被拒（JWT 校验失败分支）。"""
    c = SystemClient(api_base_url, token="forged.header.signature")
    try:
        out = c.post_expect_error("/like/isLiked", {"video_id": 1}, (401, 403))
        assert not isinstance(out, list)
    finally:
        c.close()


def test_hard_auth_positive_paths_still_open(api_base_url: str):
    """对照：带合法 token 的硬认证路由 200（防止中间件全量锁死）。"""
    from framework.data_factory import register_and_login

    user = register_and_login(api_base_url, prefix="secauth")
    try:
        counts = user.client.social.counts()  # /social/getCounts（JWT）
        assert "follower_count" in counts and "vlogger_count" in counts
        feed = user.client.feed.by_following(limit=5)  # /feed/listByFollowing（JWT）
        assert "video_list" in feed
    finally:
        user.close()


def test_soft_auth_public_feeds_anonymous_ok(anon_client: SystemClient):
    """对照：软认证 Feed 路由匿名可浏览（SoftJWTAuth，token 可选）。"""
    for path, body in (
        ("/feed/listLatest", {"limit": 1}),
        ("/feed/listByTag", {"tag_name": "sec"}),
        ("/feed/listByPopularity", {"limit": 1}),
        ("/feed/listLikesCount", {"limit": 1}),
        ("/comment/listAll", {"video_id": 99999999}),
    ):
        resp = anon_client.post_ok(path, body)
        assert resp is not None, f"{path} 匿名访问失败"
