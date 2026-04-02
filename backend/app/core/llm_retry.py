"""应用层 LLM 调用重试。

在 OpenAI SDK 与 LangChain Chat 之上，按错误类型差异化退避与次数上限；并结合进程内熔断器，
对过载、限流、短暂 5xx、连接失败及网关返回的畸形 completion 做保护。
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.core.circuit_breaker import CircuitOpenError, get_llm_circuit_breaker
from app.core.config import Settings
from app.modules.memory.llm_context_budget import (
    is_context_limit_error,
    truncate_chat_messages_to_budget,
)

logger = logging.getLogger(__name__)


class RetryStrategy(str, Enum):
    """重试间隔形态：指数、线性、立即、不重试。"""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    IMMEDIATE = "immediate"
    NONE = "none"


@dataclass(frozen=True)
class LlmRetryPolicy:
    """单次失败对应的重试上限与退避策略。"""

    max_attempts: int
    strategy: RetryStrategy


# 与 OpenAI / 常见代理一致的可重试 HTTP 状态
_RETRY_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

# langchain_openai 解析 completion 时对 choices=null / 缺键 抛出的文案片段（见 chat_models.base）
_NULL_CHOICES_TYPE = "null value for `choices`"
_MISSING_CHOICES_KEY = "Response missing `choices` key"


def _is_transient_langchain_completion_shape_error(exc: BaseException) -> bool:
    """判断是否为 LangChain 解析补全结果时遇到的瞬时畸形响应。"""
    msg = str(exc)
    if isinstance(exc, TypeError) and _NULL_CHOICES_TYPE in msg:
        return True
    if isinstance(exc, KeyError) and _MISSING_CHOICES_KEY in msg:
        return True
    return False


def is_retryable_llm_error(exc: BaseException) -> bool:
    """判断该异常是否适合在应用层做退避重试。"""
    if _is_transient_langchain_completion_shape_error(exc):
        return True
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in _RETRY_STATUS
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    cause = exc.__cause__
    if cause is not None and cause is not exc and isinstance(cause, BaseException):
        if is_retryable_llm_error(cause):
            return True
    ctx = exc.__context__
    if ctx is not None and ctx is not exc and isinstance(ctx, BaseException):
        if is_retryable_llm_error(ctx):
            return True
    return False


def _backoff_seconds(
    *,
    base: float,
    max_delay: float,
    attempt_after_failure: int,
) -> float:
    """计算单次重试前的等待秒数（指数上限 + 随机抖动）。"""
    exp = min(max_delay, base * (2**attempt_after_failure))
    jitter = 0.5 + random.random() * 0.5
    return min(max_delay, exp * jitter)


def _linear_wait_seconds(
    *,
    base: float,
    max_delay: float,
    attempt_after_failure: int,
) -> float:
    """线性递增等待（带轻微抖动）。"""
    step = min(max_delay, base * (1 + attempt_after_failure))
    jitter = 0.85 + random.random() * 0.3
    return min(max_delay, step * jitter)


def llm_retry_policy_for_exception(exc: BaseException, settings: Settings) -> LlmRetryPolicy:
    """按异常类型给出本轮可重试次数上限与退避策略（再与全局上限取较小者）。"""
    ceiling = max(1, int(settings.openai_retry_max_attempts))
    if isinstance(exc, APIStatusError):
        if exc.status_code == 429:
            return LlmRetryPolicy(
                max_attempts=min(5, ceiling),
                strategy=RetryStrategy.EXPONENTIAL,
            )
        if exc.status_code in {500, 502, 503, 504}:
            return LlmRetryPolicy(
                max_attempts=min(3, ceiling),
                strategy=RetryStrategy.EXPONENTIAL,
            )
    if isinstance(exc, APITimeoutError):
        return LlmRetryPolicy(
            max_attempts=min(4, ceiling),
            strategy=RetryStrategy.EXPONENTIAL,
        )
    if is_retryable_llm_error(exc):
        return LlmRetryPolicy(
            max_attempts=ceiling,
            strategy=RetryStrategy.EXPONENTIAL,
        )
    return LlmRetryPolicy(max_attempts=0, strategy=RetryStrategy.NONE)


def _retry_wait_seconds(
    policy: LlmRetryPolicy,
    *,
    settings: Settings,
    attempt_after_failure: int,
) -> float:
    """根据策略与 Settings 计算休眠秒数。"""
    base = max(0.1, float(settings.openai_retry_base_delay_sec))
    max_d = max(base, float(settings.openai_retry_max_delay_sec))
    if policy.strategy == RetryStrategy.IMMEDIATE:
        return 0.0
    if policy.strategy == RetryStrategy.LINEAR:
        return _linear_wait_seconds(
            base=base,
            max_delay=max_d,
            attempt_after_failure=attempt_after_failure,
        )
    if policy.strategy == RetryStrategy.EXPONENTIAL:
        return _backoff_seconds(
            base=base,
            max_delay=max_d,
            attempt_after_failure=attempt_after_failure,
        )
    return 0.0


async def ainvoke_with_retry(
    chat: BaseChatModel,
    messages: Sequence[BaseMessage],
    settings: Settings,
    *,
    config: dict[str, Any] | None = None,
) -> Any:
    """对非流式 Chat 调用包装可重试执行（差异化策略 + 熔断）。"""
    base_ceiling = max(1, int(settings.openai_retry_max_attempts))
    last_exc: BaseException | None = None
    fitted = truncate_chat_messages_to_budget(
        chat,
        messages,
        max_input_tokens=settings.llm_max_input_tokens,
    )
    breaker = get_llm_circuit_breaker()
    for attempt in range(base_ceiling):
        breaker.before_call()
        try:
            if config is not None:
                out = await chat.ainvoke(fitted, config=config)
            else:
                out = await chat.ainvoke(fitted)
            breaker.record_success()
            return out
        except CircuitOpenError:
            raise
        except Exception as e:
            last_exc = e
            if is_context_limit_error(e) and attempt == 0:
                fitted = truncate_chat_messages_to_budget(
                    chat,
                    messages,
                    max_input_tokens=max(256, settings.llm_max_input_tokens // 2),
                )
                logger.warning(
                    "LLM 返回上下文超限，已收紧输入预算并立即重试一次"
                )
                try:
                    breaker.before_call()
                    if config is not None:
                        out = await chat.ainvoke(fitted, config=config)
                    else:
                        out = await chat.ainvoke(fitted)
                    breaker.record_success()
                    return out
                except CircuitOpenError:
                    raise
                except Exception as e2:
                    last_exc = e2
                    e = e2

            policy = llm_retry_policy_for_exception(e, settings)
            if (
                policy.strategy == RetryStrategy.NONE
                or policy.max_attempts <= 0
                or not is_retryable_llm_error(e)
            ):
                breaker.record_failure()
                raise
            if attempt >= policy.max_attempts - 1:
                breaker.record_failure()
                raise
            breaker.record_failure()
            wait = _retry_wait_seconds(
                policy,
                settings=settings,
                attempt_after_failure=attempt,
            )
            logger.warning(
                "LLM 可重试错误（第 %s/%s 次，策略=%s）：%s；等待 %.1fs 后重试",
                attempt + 1,
                policy.max_attempts,
                policy.strategy.value,
                e,
                wait,
            )
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


async def astream_with_retry(
    chat: BaseChatModel,
    messages: Sequence[BaseMessage],
    settings: Settings,
) -> AsyncIterator[Any]:
    """对流式 Chat 调用包装可重试执行（差异化策略 + 熔断）。"""
    base_ceiling = max(1, int(settings.openai_retry_max_attempts))
    fitted = truncate_chat_messages_to_budget(
        chat,
        messages,
        max_input_tokens=settings.llm_max_input_tokens,
    )
    breaker = get_llm_circuit_breaker()
    for attempt in range(base_ceiling):
        breaker.before_call()
        chunks_emitted = False
        try:
            async for chunk in chat.astream(fitted):
                chunks_emitted = True
                yield chunk
            breaker.record_success()
            return
        except CircuitOpenError:
            raise
        except Exception as e:
            if chunks_emitted:
                breaker.record_failure()
                raise
            policy = llm_retry_policy_for_exception(e, settings)
            if (
                policy.strategy == RetryStrategy.NONE
                or policy.max_attempts <= 0
                or not is_retryable_llm_error(e)
            ):
                breaker.record_failure()
                raise
            if attempt >= policy.max_attempts - 1:
                breaker.record_failure()
                raise
            breaker.record_failure()
            wait = _retry_wait_seconds(
                policy,
                settings=settings,
                attempt_after_failure=attempt,
            )
            logger.warning(
                "LLM 流式可重试错误（第 %s/%s 次，策略=%s）：%s；等待 %.1fs 后重试",
                attempt + 1,
                policy.max_attempts,
                policy.strategy.value,
                e,
                wait,
            )
            await asyncio.sleep(wait)
