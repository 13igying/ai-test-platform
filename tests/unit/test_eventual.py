"""最终一致性等待组件的离线单元测试（不依赖后端）。"""
from __future__ import annotations

import pytest

from framework.assertions.eventual import (
    PermanentCheckError,
    WaitTimeoutError,
    wait_for,
    wait_until,
)


def test_wait_for_returns_truthy_result_immediately():
    assert wait_for(lambda: 42, timeout=1.0, interval=0.01) == 42


def test_wait_for_polls_until_condition_met():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        return calls["n"] >= 3

    assert wait_for(flaky, timeout=2.0, interval=0.01) is True
    assert calls["n"] == 3


def test_wait_for_timeout_raises_with_context():
    def never():
        return None

    with pytest.raises(WaitTimeoutError) as exc:
        wait_for(never, timeout=0.05, interval=0.01, desc="业务状态落库")
    msg = str(exc.value)
    assert "业务状态落库" in msg
    assert "尝试次数" in msg


def test_wait_for_transient_error_keeps_polling_then_times_out():
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise RuntimeError("网络抖动")

    with pytest.raises(WaitTimeoutError) as exc:
        wait_for(bad, timeout=0.05, interval=0.01, desc="轮询中")
    assert calls["n"] >= 2
    assert "RuntimeError" in str(exc.value)


def test_wait_for_permanent_error_fails_fast():
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise PermanentCheckError("契约校验失败：字段名错了")

    with pytest.raises(AssertionError) as exc:
        wait_for(broken, timeout=5.0, interval=0.01, desc="契约检查")
    assert calls["n"] == 1  # 立即终止，不再轮询
    assert "不可恢复" in str(exc.value)


def test_wait_for_custom_stop_on():
    class BusinessViolation(Exception):
        pass

    with pytest.raises(AssertionError):
        wait_for(
            lambda: (_ for _ in ()).throw(BusinessViolation("破坏")),
            timeout=5.0,
            interval=0.01,
            stop_on=(BusinessViolation,),
            desc="自定义终止",
        )


def test_wait_for_observe_summary_in_timeout():
    with pytest.raises(WaitTimeoutError) as exc:
        wait_for(
            lambda: [],  # 空列表 = 未达到（注意：非空 dict/list 才是真值）
            timeout=0.05,
            interval=0.01,
            observe=lambda value: len(value),
            desc="视频出现",
        )
    assert "0" in str(exc.value)  # 最后观测摘要（列表长度 0）出现在超时信息里


def test_wait_until_v2_compat_returns_true():
    assert wait_until(lambda: 1, timeout=1.0, interval=0.01) is True
