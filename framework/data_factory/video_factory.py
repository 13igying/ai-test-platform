"""视频工厂：批量造数（Feed 分页 / 热度 / 关注流等场景的数据底盘）。"""
from __future__ import annotations

import uuid
from time import sleep

from framework.clients.base_client import SystemClient
from framework.data_factory.user_factory import User
from framework.observability.allure_ext import allure, attach_json


def make_video_payload() -> dict:
    """生成视频发布 payload（play_url 方式，无需真实文件上传）。"""
    tag = uuid.uuid4().hex[:6]
    return {
        "title": f"自动化测试视频_{tag}",
        "description": f"e2e-auto-{tag} 自动化测试创建的视频",
        "play_url": f"http://example.com/videos/{tag}.mp4",
        "cover_url": f"http://example.com/covers/{tag}.jpg",
    }


def publish_video(base_url: str, user: User, **overrides) -> dict:
    """以 user 身份发布一个视频，返回发布响应（含 id）。"""
    with allure.step(f"测试数据工厂：发布视频（作者={user.username}）"):
        payload = make_video_payload()
        payload.update(overrides)
        c = user.client or user.auth_client(base_url)
        resp = c.video.publish(**payload)
        attach_json("[工厂] 发布结果", resp)
        return resp


def publish_videos(
    base_url: str,
    user: User,
    count: int,
    interval: float = 1.05,
) -> list[dict]:
    """批量发布 count 个视频，间隔 interval 秒。

    为什么默认间隔 >1s：视频 create_time 精度为秒级，连续发布会出现
    相同 create_time，Feed 游标分页（以 create_time 为序）可能乱序/漏行；
    造数时间错开是保证"分页一致性用例"数据质量的前提。
    """
    payloads: list[dict] = []
    for i in range(count):
        payloads.append(publish_video(base_url, user, title=f"批量视频_{uuid.uuid4().hex[:6]}_{i}"))
        if i < count - 1:
            sleep(interval)
    return payloads
