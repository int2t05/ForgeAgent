"""应用层 LLM 调用重试。

在 OpenAI SDK 与 LangChain Chat 之上，对过载、限流、短暂 5xx、连接失败及网关返回的畸形
completion（如 choices 为 null）做指数退避重试，供路由、规划、ReAct、流式总结等复用。
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.core.config import Settings
from app.core.llm_context_budget import (
    is_context_limit_error,
    truncate_chat_messages_to_budget,
)

logger = logging.getLogger(__name__)

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


async def ainvoke_with_retry(
    chat: BaseChatModel,
    messages: Sequence[BaseMessage],
    settings: Settings,
    *,
    config: dict[str, Any] | None = None,
) -> Any:
    """对非流式 Chat 调用包装可重试执行。"""
    max_attempts = max(1, int(settings.openai_retry_max_attempts))
    base = max(0.1, float(settings.openai_retry_base_delay_sec))
    max_d = max(base, float(settings.openai_retry_max_delay_sec))
    last_exc: BaseException | None = None
    fitted = truncate_chat_messages_to_budget(
        chat,
        messages,
        max_input_tokens=settings.llm_max_input_tokens,
    )
    for attempt in range(max_attempts):
        try:
            if config is not None:
                return await chat.ainvoke(fitted, config=config)
            return await chat.ainvoke(fitted)
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
                    if config is not None:
                        return await chat.ainvoke(fitted, config=config)
                    return await chat.ainvoke(fitted)
                except Exception as e2:
                    last_exc = e2
                    e = e2
            if not is_retryable_llm_error(e) or attempt >= max_attempts - 1:
                raise
            wait = _backoff_seconds(
                base=base, max_delay=max_d, attempt_after_failure=attempt
            )
            logger.warning(
                "LLM 可重试错误（第 %s/%s 次）：%s；等待 %.1fs 后重试",
                attempt + 1,
                max_attempts,
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
    """对流式 Chat 调用包装可重试执行。"""
    max_attempts = max(1, int(settings.openai_retry_max_attempts))
    base = max(0.1, float(settings.openai_retry_base_delay_sec))
    max_d = max(base, float(settings.openai_retry_max_delay_sec))
    fitted = truncate_chat_messages_to_budget(
        chat,
        messages,
        max_input_tokens=settings.llm_max_input_tokens,
    )
    for attempt in range(max_attempts):
        chunks_emitted = False
        try:
            async for chunk in chat.astream(fitted):
                chunks_emitted = True
                yield chunk
            return
        except Exception as e:
            # 已向下游输出过 token 则不再整流重试，避免重复片段
            if chunks_emitted:
                raise  # 手动抛出异常的关键字
            if not is_retryable_llm_error(e):
                raise
            if attempt >= max_attempts - 1:
                raise
            wait = _backoff_seconds(
                base=base, max_delay=max_d, attempt_after_failure=attempt
            )
            logger.warning(
                "LLM 流式可重试错误（第 %s/%s 次）：%s；等待 %.1fs 后重试",
                attempt + 1,
                max_attempts,
                e,
                wait,
            )
            await asyncio.sleep(wait)
