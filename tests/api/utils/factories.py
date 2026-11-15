"""兼容 shim：数据工厂已迁移到 framework.data_factory（旧导入路径过渡期保留）。"""
from framework.assertions.eventual import wait_for as wait_until  # noqa: F401
from framework.data_factory.user_factory import (  # noqa: F401
    User,
    register_and_login,
    unique_password,
    unique_username,
)
from framework.data_factory.video_factory import (  # noqa: F401
    make_video_payload,
    publish_video,
)

__all__ = [
    "User",
    "register_and_login",
    "unique_username",
    "unique_password",
    "make_video_payload",
    "publish_video",
    "wait_until",
]
