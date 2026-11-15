"""测试数据工厂：一键创建用户 / 视频 / 社交关系（对应《改进方案》3.2）。

原则：
- 每条用例独立数据（用户名/视频标题带 uuid 后缀），可独立运行、重复运行；
- 注册接口限流 5次/小时/IP：工厂通过复用已注册用户 + 直连后端缓解；
  触发 429 时给出可读指引（make clean-ratelimit 清 Redis 限流 key）；
- 只写测试数据、不做物理清理：数据带 auto-test 标记便于辨识，
  清理由环境生命周期（compose down -v）统一负责——比反向 delete
  更可靠，也避免清理脚本自身成为新的 flaky 来源。
"""
from framework.data_factory.user_factory import (
    User,
    register_and_login,
    unique_password,
    unique_username,
)
from framework.data_factory.video_factory import (
    make_video_payload,
    publish_video,
    publish_videos,
)

__all__ = [
    "User",
    "register_and_login",
    "unique_password",
    "unique_username",
    "make_video_payload",
    "publish_video",
    "publish_videos",
]
