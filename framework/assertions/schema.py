"""响应结构契约（jsonschema）：把"接口返回什么形状"固化为可校验的代码。

设计取舍（面试可讲）：
- 只锁「契约字段」：required 核心字段 + 类型，不锁全部字段
  （additionalProperties 默认放开），后端加字段不红、改名/改类型必红——
  契约校验防"破坏"，不防"演进"；
- 字段名/类型与后端 entity 逐一核对：
  feed/entity.go、account/entity.go、social/entity.go、video/video_entity.go；
- 同名字段类型可能不同，必须分开建模：FeedVideoItem.create_time 是 int64
  时间戳（秒），而 getDetail 返回的 Video.create_time 是 time.Time 序列化的
  RFC3339 字符串——这是两种不同的契约，混用会误报。

使用方式：BaseClient.post_ok(..., schema="login")，校验失败抛 AssertionError，
错误信息含违规 JSON 路径与原因，可精确定位到字段。
"""
from __future__ import annotations

import jsonschema

# ---- 可复用的子结构 ----

_FEED_AUTHOR = {
    "type": "object",
    "required": ["id", "username"],
    "properties": {
        "id": {"type": "integer"},
        "username": {"type": "string"},
    },
}

_FEED_VIDEO_ITEM = {
    "type": "object",
    "required": ["id", "author", "title", "play_url", "cover_url", "create_time", "likes_count", "is_liked"],
    "properties": {
        "id": {"type": "integer"},
        "author": _FEED_AUTHOR,
        "title": {"type": "string"},
        "description": {"type": "string"},
        "play_url": {"type": "string"},
        "cover_url": {"type": "string"},
        "create_time": {"type": "integer"},  # FeedVideoItem.CreateTime int64（秒级时间戳）
        "likes_count": {"type": "integer"},
        "is_liked": {"type": "boolean"},
    },
}

# listLatest / listLikesCount / listByFollowing 共用：
# 游标字段（next_time / next_likes_count_before / next_id_before）按各自接口可选，
# 契约核心是 video_list 数组结构 + has_more 布尔。
_FEED = {
    "type": "object",
    "required": ["video_list", "has_more"],
    "properties": {
        "video_list": {"type": "array", "items": _FEED_VIDEO_ITEM},
        "has_more": {"type": "boolean"},
        "next_time": {"type": "integer"},
        "next_likes_count_before": {"type": "integer"},
        "next_id_before": {"type": "integer"},
    },
}

# ---- 各接口契约（对齐后端 handler/entity）----

LOGIN = {  # account.LoginResponse
    "type": "object",
    "required": ["token", "refresh_token", "account_id", "username"],
    "properties": {
        "token": {"type": "string"},
        "refresh_token": {"type": "string"},
        "account_id": {"type": "integer"},
        "username": {"type": "string"},
    },
}

REGISTER = {  # CreateAccount -> {"message": "account created"}
    "type": "object",
    "required": ["message"],
    "properties": {"message": {"type": "string"}},
}

VIDEO_DETAIL = {  # getDetail 返回裸 video.Video：create_time 为 time.Time -> RFC3339 字符串
    "type": "object",
    "required": ["id", "author_id", "username", "title", "play_url", "cover_url", "create_time", "likes_count"],
    "properties": {
        "id": {"type": "integer"},
        "author_id": {"type": "integer"},
        "username": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "play_url": {"type": "string"},
        "cover_url": {"type": "string"},
        "create_time": {"type": "string"},
        "likes_count": {"type": "integer"},
        "popularity": {"type": "integer"},
    },
}

IS_LIKED = {  # IsLiked -> {"is_liked": bool}
    "type": "object",
    "required": ["is_liked"],
    "properties": {"is_liked": {"type": "boolean"}},
}

FOLLOWERS = {  # GetAllFollowersResponse
    "type": "object",
    "required": ["followers", "follower_count"],
    "properties": {
        "followers": {
            "type": "array",
            "items": {"type": "object", "required": ["id", "username"]},
        },
        "follower_count": {"type": "integer"},
    },
}

SOCIAL_COUNTS = {  # SocialCounts（getCounts，基于 JWT）
    "type": "object",
    "required": ["follower_count", "vlogger_count"],
    "properties": {
        "follower_count": {"type": "integer"},
        "vlogger_count": {"type": "integer"},
    },
}

BUG = {  # bugtracker.Bug
    "type": "object",
    "required": ["id", "title", "severity", "status", "reporter_id", "assignee_id"],
    "properties": {
        "id": {"type": "integer"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "severity": {"type": "string"},
        "status": {"type": "string"},
        "reporter_id": {"type": "integer"},
        "assignee_id": {"type": "integer"},
    },
}

BUG_LIST = {
    "type": "object",
    "required": ["bugs", "total"],
    "properties": {
        "bugs": {"type": "array", "items": BUG},
        "total": {"type": "integer"},
    },
}

# ---- 注册表：post_ok(schema="名字") 即校验 ----

SCHEMAS: dict[str, dict] = {
    "register": REGISTER,
    "login": LOGIN,
    "feed": _FEED,
    "video_detail": VIDEO_DETAIL,
    "is_liked": IS_LIKED,
    "followers": FOLLOWERS,
    "social_counts": SOCIAL_COUNTS,
    "bug": BUG,
    "bug_list": BUG_LIST,
}


def _violation_path(err: jsonschema.ValidationError) -> str:
    """把 ValidationError 的路径渲染成 $.video_list.0.id 这样可读的 JSON 路径。"""
    path = "$"
    for part in err.absolute_path:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def validate_schema(payload, name: str) -> None:
    """校验 payload 是否符合注册表中的契约；失败抛 AssertionError（pytest 原生判失败）。"""
    schema = SCHEMAS.get(name)
    if schema is None:
        raise KeyError(f"未注册的 schema: {name!r}，可选: {sorted(SCHEMAS)}")
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.ValidationError as err:
        raise AssertionError(
            f"[契约] 响应不符合结构 '{name}'"
            f"\n[契约] 违规位置: {_violation_path(err)}"
            f"\n[契约] 原因: {err.message}"
        ) from err
