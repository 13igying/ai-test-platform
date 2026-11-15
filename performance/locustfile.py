"""Feed 核心接口的 Locust 性能脚本（读多写少场景）。

运行（本机示例）：
    locust -f performance/locustfile.py --host http://127.0.0.1:8080 \
           --headless -u 20 -r 2 -t 30s --csv reports/locust
远程环境：
    locust -f performance/locustfile.py --host http://<服务器>:8080 --headless ...

设计：
- FeedReader（weight=4）：纯读流量，覆盖 4 条 feed 流 + 视频详情（Redis 缓存路径）；
- FeedInteractor（weight=1）：注册/登录后做点赞-取消循环，覆盖写路径与
  MQ 链路（后端 like 写限流 30次/分钟/账号，wait_time 已按此放宽）；
- 视频样本池：reader 巡检最新流时回填，interactor 从池里取样互动，
  避免构造多余数据（性能测试不清理数据，跑完 compose down -v 统一回收）。
"""
from __future__ import annotations

import random
import uuid

from locust import HttpUser, between, task

READ_WAIT = between(0.5, 2.0)
WRITE_WAIT = between(2.0, 5.0)

# 进程内共享的视频样本池（reader 回填 / interactor 取样）
VIDEO_POOL: list[int] = []


class FeedReader(HttpUser):
    """匿名读流量（软认证路由，无需 token）。"""

    weight = 4
    wait_time = READ_WAIT

    @task(4)
    def list_latest(self):
        with self.client.post(
            "/feed/listLatest", json={"limit": 10}, name="POST /feed/listLatest [w4]"
        ) as resp:
            data = None
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    pass
            if data and data.get("video_list"):
                for v in random.sample(data["video_list"], min(3, len(data["video_list"]))):
                    if v.get("id") and v["id"] not in VIDEO_POOL:
                        VIDEO_POOL.append(int(v["id"]))
                del VIDEO_POOL[:-500]  # 控制池大小

    @task(2)
    def list_by_likes(self):
        self.client.post("/feed/listLikesCount", json={"limit": 10}, name="POST /feed/listLikesCount [w2]")

    @task(1)
    def list_by_popularity(self):
        self.client.post("/feed/listByPopularity", json={"limit": 10}, name="POST /feed/listByPopularity [w1]")

    @task(1)
    def list_by_tag(self):
        self.client.post("/feed/listByTag", json={"tag_name": "demo"}, name="POST /feed/listByTag [w1]")

    @task(2)
    def video_detail(self):
        if not VIDEO_POOL:
            return
        vid = random.choice(VIDEO_POOL)
        self.client.post("/video/getDetail", json={"id": vid}, name="POST /video/getDetail [w2]")


class FeedInteractor(HttpUser):
    """认证写流量：注册登录 → 点赞/取消循环（写限流 30/min/账号）。"""

    weight = 1
    wait_time = WRITE_WAIT

    def on_start(self):
        username = f"locust_{uuid.uuid4().hex[:10]}"
        password = "Test#" + uuid.uuid4().hex[:8]
        with self.client.post(
            "/account/register",
            json={"username": username, "password": password},
            name="POST /account/register [setup]",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"注册失败 HTTP {resp.status_code}")
        with self.client.post(
            "/account/login",
            json={"username": username, "password": password},
            name="POST /account/login [setup]",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"登录失败 HTTP {resp.status_code}")
                return
            token = resp.json().get("token")
        self.client.headers["Authorization"] = f"Bearer {token}"

    @task(3)
    def like_unlike_cycle(self):
        if not VIDEO_POOL:
            return
        vid = random.choice(VIDEO_POOL)
        self.client.post("/like/like", json={"video_id": vid}, name="POST /like/like [w1]")
        self.client.post("/like/unlike", json={"video_id": vid}, name="POST /like/unlike [w1]")

    @task(1)
    def check_my_liked(self):
        self.client.post("/like/listMyLikedVideos", json={"limit": 5}, name="POST /like/listMyLikedVideos [w1]")
