"""进程内熔断器：连续失败达阈值时短时拒绝新请求，减轻 LLM / 工具层的级联过载。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CircuitState(str, Enum):
    """熔断器三态：正常、熔断拒绝、半开试恢复。"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """熔断开启且尚未进入允许探测时抛出，调用方应中止或降级。"""


@dataclass
class CircuitBreaker:
    """简易熔断器：失败累加至阈值则打开；超时后半开允许探测，成功关闭、失败再开。"""

    name: str
    failure_threshold: int = 5
    recovery_timeout_sec: float = 60.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: datetime | None = field(default=None, init=False)

    def record_success(self) -> None:
        """登记成功：关闭熔断并清零失败计数。"""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        """登记失败：半开态探测失败直接再开；闭合态累加至阈值则打开。"""
        now = datetime.now(timezone.utc)
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = now
            return
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = now

    def before_call(self) -> None:
        """若当前不可执行则抛出 ``CircuitOpenError``；打开状态超时后进入半开。"""
        now = datetime.now(timezone.utc)
        if self._state == CircuitState.CLOSED:
            return
        if self._state == CircuitState.HALF_OPEN:
            return
        if self._state != CircuitState.OPEN:
            return
        if self._opened_at is None:
            self._state = CircuitState.HALF_OPEN
            return
        elapsed = (now - self._opened_at).total_seconds()
        if elapsed >= self.recovery_timeout_sec:
            self._state = CircuitState.HALF_OPEN
            return
        raise CircuitOpenError(
            f"熔断器 [{self.name}] 已打开，约 {int(self.recovery_timeout_sec - elapsed)}s 后可重试"
        )


_llm_breaker = CircuitBreaker(name="llm")
_tool_breaker = CircuitBreaker(name="tools", failure_threshold=10)


def get_llm_circuit_breaker() -> CircuitBreaker:
    """返回进程内 LLM 调用共用熔断器实例（阈值随当前 ``Settings`` 同步）。"""
    from app.core.config import get_settings

    s = get_settings()
    _llm_breaker.failure_threshold = max(1, int(s.circuit_breaker_llm_failure_threshold))
    _llm_breaker.recovery_timeout_sec = max(1.0, float(s.circuit_breaker_llm_recovery_sec))
    return _llm_breaker


def get_tool_circuit_breaker() -> CircuitBreaker:
    """返回进程内工具执行共用熔断器实例（阈值随当前 ``Settings`` 同步）。"""
    from app.core.config import get_settings

    s = get_settings()
    _tool_breaker.failure_threshold = max(1, int(s.circuit_breaker_tool_failure_threshold))
    _tool_breaker.recovery_timeout_sec = max(1.0, float(s.circuit_breaker_tool_recovery_sec))
    return _tool_breaker
