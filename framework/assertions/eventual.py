"""最终一致性等待组件 v3（对应《改进方案》3.3：重构异步等待与断言）。

核心观点：HTTP 返回成功 ≠ 业务状态完成；业务状态完成也不一定说明
所有异步链路都已完成。应根据真实业务契约明确最终要验证的状态。

v3 相对 v2 的升级（面试重点）：
1. time.monotonic() 计时（v2 已有，保留）——不受 NTP 对时回拨影响；
2. 可配置：最大等待时长、轮询间隔、可重试异常集合；
3. 区分"暂时未达到目标状态"与"真实的不可恢复错误"：
   - transient（默认 Exception）：网络抖动、偶发 5xx → 继续等；
   - permanent（PermanentCheckError / 显式 stop_on）：业务契约被破坏、
     契约校验失败 → 立即终止。继续等只会把 1 分钟的失败拖成 1 分钟的
     假等待，还掩盖真实错误类型。
4. 超时异常携带完整现场：最后观测值、最后异常、尝试次数、关联
   request_id——失败信息即排查现场；
5. 轮询记录写入 EvidenceStore，供失败证据与 AI 分析消费；
6. 场景无关：视频发布落库、消息消费、缓存更新……统一这一个入口。

新代码一律用 wait_for()；wait_until() 是 v2 兼容签名（全部异常视为
transient），存量用例零改动。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Iterable, TypeVar

from framework.observability.allure_ext import allure
from framework.observability.evidence import store

T = TypeVar("T")


class PermanentCheckError(Exception):
    """显式声明"不可恢复"：轮询再等下去没有意义，立即失败。

    用法：条件函数内部检测到业务契约被破坏时抛出，例如
    - 发布接口返回了成功，但视频记录被删除（而非尚未落库）；
    - 响应结构契约校验失败（schema 违规是确定性错误，不是时序问题）。
    """


class WaitTimeoutError(AssertionError):
    """轮询超时：继承 AssertionError 让 pytest 判失败，携带完整排查现场。"""

    def __init__(
        self,
        desc: str,
        timeout: float,
        attempts: int,
        last_observed: Any,
        last_error: Exception | None,
        request_ids: list[str],
    ) -> None:
        detail = (
            f"\n[等待目标] {desc}"
            f"\n[超时阈值] {timeout}s（time.monotonic 计时）"
            f"\n[尝试次数] {attempts}"
            f"\n[最后观测] {last_observed!r}"
        )
        if last_error is not None:
            detail += f"\n[最后异常] {type(last_error).__name__}: {last_error}"
        if request_ids:
            detail += f"\n[request_id] {', '.join(request_ids[-5:])}"
        else:
            detail += "\n[request_id] 无（该条件函数未发起可关联请求）"
        super().__init__(detail)


def wait_for(
    condition: Callable[[], T],
    *,
    timeout: float = 10.0,
    interval: float = 0.5,
    desc: str = "条件成立",
    stop_on: Iterable[type[BaseException]] = (PermanentCheckError,),
    observe: Callable[[T], Any] | None = None,
) -> T:
    """轮询 condition 直到其返回真值；返回最后一次（真值）结果。

    参数：
        condition : 轮询条件，返回真值即通过；抛 PermanentCheckError 或
                    stop_on 中异常时立即终止（真实错误 ≠ 未就绪）；
        timeout   : 最大等待秒数（monotonic 计时）；
        interval  : 轮询间隔秒数；
        desc      : 业务描述（进 Allure 步骤与超时信息）；
        stop_on   : 不可恢复异常类型集合（默认仅 PermanentCheckError）；
        observe   : 可选，把每次观测值转成可读摘要（进证据/超时信息），
                    例如 lambda feed: len(feed["video_list"])。

    超时抛 WaitTimeoutError（含最后观测值/最后异常/尝试次数/request_id）。
    """
    permanent = tuple(stop_on)
    deadline = time.monotonic() + timeout
    attempts = 0
    last_observed: Any = None
    last_error: Exception | None = None

    with allure.step(f"轮询等待异步链路：{desc}（超时 {timeout}s）"):
        while time.monotonic() < deadline:
            attempts += 1
            try:
                last_observed = condition()
                if last_observed:
                    store.record_poll(
                        {"desc": desc, "attempts": attempts, "result": "met", "observed": _obs(observe, last_observed)}
                    )
                    return last_observed
            except permanent as exc:  # 真实的不可恢复错误：立即失败
                store.record_poll(
                    {"desc": desc, "attempts": attempts, "result": "permanent_error", "error": repr(exc)}
                )
                raise AssertionError(
                    f"\n[不可恢复错误] 等待目标：{desc}"
                    f"\n[第 {attempts} 次观测] {type(exc).__name__}: {exc}"
                    f"\n[结论] 该错误不是异步时序问题，继续等待无意义"
                ) from exc
            except Exception as exc:  # noqa: BLE001 —— transient：视为未就绪，继续等
                last_error = exc
                last_observed = None
            time.sleep(interval)

        store.record_poll(
            {"desc": desc, "attempts": attempts, "result": "timeout", "observed": _obs(observe, last_observed)}
        )
        raise WaitTimeoutError(
            desc=desc,
            timeout=timeout,
            attempts=attempts,
            last_observed=_obs(observe, last_observed),
            last_error=last_error,
            request_ids=list(store.snapshot().get("request_ids", [])),
        )


def _obs(observe: Callable[[T], Any] | None, value: Any) -> Any:
    try:
        return observe(value) if observe is not None else value
    except Exception:  # 观测摘要失败不影响主流程
        return value


def wait_until(
    fn: Callable[[], Any],
    timeout: float = 10.0,
    interval: float = 0.5,
    desc: str = "条件成立",
) -> bool:
    """v2 兼容签名：所有异常一律视为 transient（历史行为），供存量用例零改动。"""
    wait_for(fn, timeout=timeout, interval=interval, desc=desc)
    return True
