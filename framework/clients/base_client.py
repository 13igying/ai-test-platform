"""BaseClient：httpx 封装 + 业务子客户端组合。

每次请求统一做五件事（对应《改进方案》3.1）：
1. 生成测试侧 request_id（X-Request-Id 头），用于与后台日志关联——
   后端当前未透传该标识，证据中会显式标注 missing_evidence，
   这是"跨链路证据关联"改造的后端待办（改进方案 5.3 第二步）；
2. 计时并构造脱敏后的 Exchange 记录 → EvidenceStore（失败证据）；
3. 请求/响应挂 Allure 附件（只附业务数据，Authorization 不进报告）；
4. 统一错误抛出：APIError（继承 AssertionError，pytest 原生判失败）；
5. 可选响应结构契约校验（schema=）。

post_ok 的 schema 校验失败属于"契约破坏"，是确定性错误——后续
wait_for(stop_on=(APIError,)) 可把它与异步时序问题区分开。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from framework.assertions.schema import validate_schema
from framework.observability.allure_ext import allure, attach_json, attach_text
from framework.observability.evidence import store
from framework.observability.redact import redact_headers, redact_obj, truncate

from framework.clients.account_api import AccountAPI
from framework.clients.bug_api import BugAPI
from framework.clients.feed_api import FeedAPI
from framework.clients.social_api import SocialAPI
from framework.clients.video_api import VideoAPI


class APIError(AssertionError):
    """接口返回非预期结果时抛出，附带请求/响应详情（继承 AssertionError）。"""


class BaseClient:
    """轻量 API 客户端基类（每条用例独立实例，用例间互不共享连接/登录态）。"""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=self.base_url, headers=self._headers, timeout=timeout
        )
        self.timeout = timeout

        # 业务子客户端视图：client.feed.latest(...) / client.account.login(...) ...
        self.account = AccountAPI(self)
        self.feed = FeedAPI(self)
        self.video = VideoAPI(self)
        self.social = SocialAPI(self)
        self.bug = BugAPI(self)

    # ---------- HTTP 基础 ----------
    def _do(self, method: str, path: str, **kwargs) -> httpx.Response:
        """统一入口：request_id + 计时 + 证据 + Allure。"""
        request_id = uuid.uuid4().hex[:12]
        headers = {"X-Request-Id": request_id}
        start = time.perf_counter()
        error: str | None = None
        resp: httpx.Response | None = None
        try:
            resp = self._http.request(method, path, headers=headers, **kwargs)
            status = resp.status_code
            resp_summary = truncate(resp.text)
        except httpx.HTTPError as exc:
            status = 0
            resp_summary = f"{type(exc).__name__}: {exc}"
            error = resp_summary
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        # 后端尚未读取/透传 X-Request-Id：显式标注证据缺口，供 AI 分析声明
        store.note_missing("backend 未透传 X-Request-Id 到响应头/日志（跨链路关联待后端支持）")

        exchange = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "request_id": request_id,
            "method": method,
            "path": path,
            "req_headers": redact_headers({**self._headers, **headers}),
            "req_body": redact_obj(kwargs.get("json") or kwargs.get("data") or {}),
            "status": status,
            "duration_ms": duration_ms,
            "resp_body": resp_summary,
        }
        if error:
            exchange["error"] = error
        store.record_exchange(exchange)

        label = f"{method} {path}" + ("(multipart)" if kwargs.get("files") else "")
        with allure.step(f"{label} -> {status}"):
            attach_json(f"[请求] {label}", {"request_id": request_id, **exchange["req_body"]})
            attach_text(f"[响应] {label} -> {status}", resp_summary)

        if resp is None:  # 网络层异常：统一抛 APIError，断言现场完整
            raise APIError(
                f"\n[请求失败] {method} {path}"
                f"\n[request_id] {request_id}"
                f"\n[异常] {error}"
            )
        resp.headers["x-test-request-id"] = request_id  # 回填，供测试侧关联
        return resp

    def post(self, path: str, json_body: dict | None = None, **kwargs) -> httpx.Response:
        return self._do("POST", path, json=json_body if json_body is not None else {}, **kwargs)

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._do("GET", path, **kwargs)

    def post_multipart(self, path: str, data: dict, files: dict, **kwargs) -> httpx.Response:
        """multipart 上传（自动移除 Content-Type，交由 httpx 生成 boundary）。"""
        kwargs.pop("headers", None)
        return self._do("POST", path, data=data, files=files or {}, **kwargs)

    def close(self) -> None:
        self._http.close()

    # ---------- 断言辅助 ----------
    def post_ok(
        self,
        path: str,
        json_body: dict | None = None,
        expect: int = 200,
        schema: str | None = None,
    ) -> dict:
        """POST 并断言状态码，返回 JSON dict；schema 可选契约校验。"""
        resp = self.post(path, json_body)
        if resp.status_code != expect:
            raise APIError(
                f"\n[请求] POST {path} body={json_body}"
                f"\n[响应] {resp.status_code} {resp.text[:500]}"
            )
        return self._json_or_error(resp, path, schema)

    def get_json(self, path: str, schema: str | None = None, **kwargs) -> dict:
        """GET 并断言 200，返回 JSON dict。"""
        resp = self.get(path, **kwargs)
        if resp.status_code != 200:
            raise APIError(f"\n[请求] GET {path}\n[响应] {resp.status_code} {resp.text[:500]}")
        return self._json_or_error(resp, path, schema)

    def post_expect_error(
        self, path: str, json_body: dict | None, expect_status: int | tuple[int, ...]
    ) -> dict:
        """POST 并断言返回错误状态码（401/400/403/429 等）。

        expect_status 传元组可同时接受多个"可接受的拒绝码"，
        如 (401, 403)：后端对"未授权"任选其一，语义都是"被授权体系拒绝"。
        """
        resp = self.post(path, json_body)
        allowed = expect_status if isinstance(expect_status, tuple) else (expect_status,)
        assert (
            resp.status_code in allowed
        ), f"[期望 {'|'.join(str(s) for s in allowed)}] POST {path} body={json_body} -> 实际 {resp.status_code} {resp.text[:300]}"
        try:
            return resp.json()
        except json.JSONDecodeError:
            return {}

    def _json_or_error(self, resp: httpx.Response, path: str, schema: str | None) -> dict:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise APIError(f"[响应非 JSON] {path} -> {resp.text[:300]}")
        if schema:
            validate_schema(data, schema)
            with allure.step(f"响应结构契约 '{schema}' 校验通过"):
                pass
        return data

    # ---------- 认证 ----------
    def set_token(self, token: str | None):
        """绑定/清除 token（同步修改 httpx.Client headers，构造时快照否则无效）。"""
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
            self._http.headers["Authorization"] = f"Bearer {token}"
        else:
            self._headers.pop("Authorization", None)
            self._http.headers.pop("Authorization", None)

    @property
    def token(self) -> str | None:
        return self._headers.get("Authorization", "").removeprefix("Bearer ") or None


class SystemClient(
    BaseClient, AccountAPI, FeedAPI, VideoAPI, SocialAPI, BugAPI
):
    """组合全部业务能力的统一客户端。

    - 子客户端视图：client.feed.latest(...)（新代码推荐，职责清晰）；
    - 平铺方法：client.feed_latest(...)（v1 兼容，存量脚本/Web 运行器零改动）。
    """


# 向后兼容：旧代码 / 兼容 shim 用的名字
APIClient = SystemClient

