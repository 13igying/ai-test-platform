"""脱敏（redaction）：任何进入证据/报告/LLM 的数据必须先过这里。

为什么放在 observability 而不是各 client 里：
- 脱敏规则只有一份（密钥类字段名单），client、证据、AI 分析共用；
- AI 模块把证据喂给大模型前也必须复用同一规则——密码/token 永远
  不应该出现在任何报告、日志或 LLM 请求里。
"""
from __future__ import annotations

from typing import Any

# 命中（大小写不敏感）即打码的字段名
SENSITIVE_KEYS = {
    "password",
    "token",
    "authorization",
    "refresh_token",
    "access_token",
    "secret",
    "api_key",
    "webhook",
}
MASK = "******"
# 证据里的长文本截断阈值（控制证据文件体积，也控制 LLM 输入成本）
MAX_TEXT_LEN = 2000


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in SENSITIVE_KEYS)


def redact_obj(obj: Any, _depth: int = 0) -> Any:
    """递归脱敏 dict/list；其他原样返回。超深层级直接 repr，防止循环引用。"""
    if _depth > 8:
        return repr(obj)[:MAX_TEXT_LEN]
    if isinstance(obj, dict):
        return {
            k: (MASK if _is_sensitive(str(k)) else redact_obj(v, _depth + 1))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v, _depth + 1) for v in obj]
    return obj


def redact_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """HTTP 头脱敏：Authorization 只保留认证方案，其余敏感头打码。"""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if k.lower() == "authorization":
            scheme = v.split(" ", 1)[0] if " " in v else "Bearer"
            out[k] = f"{scheme} {MASK}"
        elif _is_sensitive(k):
            out[k] = MASK
        else:
            out[k] = v
    return out


def deep_redact(obj: Any, _depth: int = 0) -> Any:
    """递归脱敏 + 超长文本截断：进入 LLM 输入 / 落盘前的最后一道处理。

    与 redact_obj 的区别：对最终是字符串的叶子额外做 truncate——
    LLM 上下文和证据文件都不需要完整的大响应体。
    """
    out = redact_obj(obj, _depth)
    if isinstance(out, str):
        return truncate(out)
    if isinstance(out, dict):
        return {k: deep_redact(v, _depth + 1) for k, v in out.items()}
    if isinstance(out, (list, tuple)):
        return [deep_redact(v, _depth + 1) for v in out]
    return out


def truncate(text: str | None, limit: int = MAX_TEXT_LEN) -> str:
    """长文本截断并标注，防止单条证据膨胀（也保护 LLM 上下文窗口）。"""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"
