"""LLM 网关：所有大模型调用走这一个口子（对应《改进方案》4.1 第一层）。

设计要点：
- OpenAI 兼容协议（/chat/completions），换模型只改环境变量 AI_LLM_*；
- 未配置 Key 时 mode="offline"，调用 chat_json 直接抛 OfflineModeError——
  调用方（generator/analyzer）捕获后降级为确定性 rules_only 路径，
  全平台在无 Key 环境依旧可完整演示（CI 与面试环境的关键约束）；
- 超时/限流/坏响应统一抛 GatewayError，调用方降级而非崩溃；
- 解析宽容：剥掉 ```json 围栏、截取首个平衡的 JSON 对象/数组——
  LLM 输出格式不可控是常态，网关层负责把"能救的输出"救回来。
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from framework.config import get_settings


class OfflineModeError(Exception):
    """未配置 LLM（offline 模式）时调用远端能力。"""


class GatewayError(Exception):
    """LLM 网关调用失败（网络/超时/响应不可解析）。"""


class LLMGateway:
    """进程内共享的 LLM 网关（无状态，可直接实例化）。"""

    def __init__(self, settings=None, timeout: float = 180.0) -> None:
        # 默认 180s:批量生成 JSON 用例实测很慢(6 条 >120s,3 条可在 120s 内),30s 必超时
        self._settings = settings if settings is not None else get_settings()
        self._timeout = timeout

    # ---------- 状态 ----------
    @property
    def mode(self) -> str:
        return "remote" if self._settings.llm_configured else "offline"

    @property
    def model(self) -> str:
        return self._settings.llm_model

    # ---------- 调用 ----------
    def chat_json(self, system: str, user: str, temperature: float = 0.2) -> Any:
        """请求 LLM 并解析出 JSON（dict 或 list）；offline 模式抛 OfflineModeError。

        非流式优先；若因服务端对长生成的空闲超时被掐断（ReadTimeout 等），
        自动降级为 SSE 流式重试——chunk 持续到达使连接永不空闲，
        不受推理网关对非流式请求的空闲时限约束。
        """
        if not self._settings.llm_configured:
            raise OfflineModeError(
                "未配置 AI_LLM_BASE_URL / AI_LLM_API_KEY（offline 模式），"
                "调用方应降级为确定性 rules_only 路径"
            )
        payload = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        try:
            resp = self._post(url, payload, headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if content is None:
                raise ValueError("choices[0].message.content 为 null")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            content = self._post_stream_collect(url, payload, headers, reason=exc)
        return extract_json(content)

    def _post_stream_collect(self, url: str, payload: dict, headers: dict, reason: Exception) -> str:
        """SSE 流式兜底：拼接 delta.content 后交回 extract_json 解析。"""
        stream_payload = {**payload, "stream": True}
        parts: list[str] = []
        try:
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream("POST", url, json=stream_payload, headers=headers) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        line = (line or "").strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if delta:
                            parts.append(delta)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as stream_exc:
            raise GatewayError(
                f"LLM 请求失败（非流式: {type(reason).__name__}: {reason}; "
                f"流式: {type(stream_exc).__name__}: {stream_exc}）"
            ) from stream_exc
        content = "".join(parts)
        if not content:
            raise GatewayError("流式响应未产生任何内容")
        return content

    # ---------- 测试辅助 ----------
    def with_transport(self, transport: httpx.BaseTransport) -> "LLMGateway":
        """注入自定义 transport（单测用 httpx.MockTransport 模拟远端）。"""
        self._transport = transport
        return self

    def _post(self, url: str, payload: dict, headers: dict) -> httpx.Response:
        transport = getattr(self, "_transport", None)
        if transport is not None:  # 测试路径：MockTransport 需要 Client 承载
            with httpx.Client(transport=transport, timeout=self._timeout) as client:
                return client.post(url, json=payload, headers=headers)
        return httpx.post(url, json=payload, headers=headers, timeout=self._timeout)


def extract_json(text: str) -> Any:
    """从 LLM 文本输出中提取 JSON：剥围栏 → 取文本中最早出现的平衡 JSON。"""
    if text is None:
        raise GatewayError("LLM 返回内容为空")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 剥 ```json ... ``` 围栏
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    # 先确定最早出现的开括号类型：避免数组里内嵌对象时误从对象开始截取
    starts = [(cleaned.find(op), op, cl) for op, cl in (("{", "}"), ("[", "]"))]
    starts = [(s, op, cl) for s, op, cl in starts if s != -1]
    if not starts:
        raise GatewayError(f"输出中未找到 JSON: {cleaned[:200]}")
    starts.sort()
    for start, opener, closer in starts:
        depth = 0
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    fragment = cleaned[start : i + 1]
                    try:
                        return json.loads(fragment)
                    except json.JSONDecodeError as exc:
                        raise GatewayError(f"JSON 解析失败: {exc}: {fragment[:200]}") from exc
    raise GatewayError(f"JSON 不平衡: {cleaned[:200]}")
