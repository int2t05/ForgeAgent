"""熔断器：闭合 / 打开 / 半开恢复与拒绝行为。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


def test_circuit_opens_after_failures() -> None:
    """连续失败达到阈值后进入打开态并拒绝调用。"""
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout_sec=3600.0)
    cb.record_failure()
    assert cb._state == CircuitState.CLOSED
    cb.record_failure()
    assert cb._state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        cb.before_call()


def test_circuit_half_open_after_recovery_time() -> None:
    """打开态超过恢复时间后进入半开，允许一次探测。"""
    cb = CircuitBreaker(name="t", failure_threshold=1, recovery_timeout_sec=0.0)
    cb._opened_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    cb._state = CircuitState.OPEN
    cb.before_call()
    assert cb._state == CircuitState.HALF_OPEN


def test_record_success_closes() -> None:
    """成功登记后关闭并清零失败计数。"""
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout_sec=60.0)
    cb.record_failure()
    cb.record_success()
    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 0
