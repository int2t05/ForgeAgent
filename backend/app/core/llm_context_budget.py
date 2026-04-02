"""LLM 输入上下文预算：在重试层统一裁剪消息，降低网关 400 上下文超限概率。"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_TAIL_HINT = "\n\n[... 已省略部分内容以适配上下文窗口 ...]"


def message_content_text(content: Any) -> str:
    """抽取消息体纯文本（与流式抽取逻辑一致的扁平化）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def estimate_messages_tokens(
    chat: BaseChatModel | None,
    messages: Sequence[BaseMessage],
) -> int:
    """估算消息列表 token 数：优先使用 Chat 模型自带计数，否则字符启发式（偏保守）。"""
    msgs = list(messages)
    if chat is not None:
        getter = getattr(chat, "get_num_tokens_from_messages", None)
        if callable(getter):
            try:
                return int(getter(msgs))
            except Exception:
                pass
    total = 0
    for m in msgs:
        total += max(1, len(message_content_text(m.content)) // 3)
    total += len(msgs) * 4
    return total


def is_context_limit_error(exc: BaseException) -> bool:
    """判断是否为供应商返回的上下文/长度类 400。"""
    s = str(exc).lower()
    return (
        "context" in s
        and ("limit" in s or "exceed" in s or "exceeds" in s or "token" in s)
    ) or "maximum context" in s


def _clone_message(msg: BaseMessage, text: str) -> BaseMessage:
    if isinstance(msg, SystemMessage):
        return SystemMessage(content=text)
    if isinstance(msg, AIMessage):
        return AIMessage(content=text)
    return HumanMessage(content=text)


def _truncate_one_message(
    chat: BaseChatModel | None,
    msg: BaseMessage,
    max_tokens: int,
) -> BaseMessage:
    """将单条消息内容收缩到不超过 max_tokens（二分长度）。"""
    text = message_content_text(msg.content)
    probe = _clone_message(msg, text)
    if estimate_messages_tokens(chat, [probe]) <= max_tokens:
        return msg
    low, high = 0, len(text)
    best = 0
    while low <= high:
        mid = (low + high) // 2
        suffix = _TAIL_HINT if mid < len(text) else ""
        cand_text = text[:mid] + suffix
        cand = _clone_message(msg, cand_text)
        if estimate_messages_tokens(chat, [cand]) <= max_tokens:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    out = text[:best] + (_TAIL_HINT if best < len(text) else "")
    return _clone_message(msg, out)


def _drop_index_after_systems(msgs: list[BaseMessage]) -> int | None:
    """返回优先丢弃的下标：领先 System 块之后最早的一条；仅 System 时丢第二条。"""
    if len(msgs) <= 1:
        return None
    i = 0
    while i < len(msgs) and isinstance(msgs[i], SystemMessage):
        i += 1
    if i < len(msgs):
        return i
    return 1 if len(msgs) > 1 else None


def truncate_chat_messages_to_budget(
    chat: BaseChatModel | None,
    messages: Sequence[BaseMessage],
    *,
    max_input_tokens: int,
) -> list[BaseMessage]:
    """将消息列表裁剪到不超过 ``max_input_tokens``：先丢最早历史，再截断单条正文。"""
    budget = max(64, int(max_input_tokens))
    msgs = list(messages)
    before = estimate_messages_tokens(chat, msgs)
    if before <= budget:
        return msgs

    iterations = 0
    while estimate_messages_tokens(chat, msgs) > budget:
        iterations += 1
        if iterations > 4096:
            logger.error("LLM 上下文裁剪异常：迭代过多，中止于当前列表")
            break
        drop_i = _drop_index_after_systems(msgs)
        if drop_i is not None:
            msgs.pop(drop_i)
            continue
        if not msgs:
            break
        msgs[0] = _truncate_one_message(chat, msgs[0], budget)
        break

    after = estimate_messages_tokens(chat, msgs)
    if after > budget and msgs:
        msgs = [_truncate_one_message(chat, msgs[0], budget)]

    after = estimate_messages_tokens(chat, msgs)
    logger.warning(
        "LLM 上下文已裁剪：估算约 %s → %s tokens（输入上限 %s）",
        before,
        after,
        budget,
    )
    return msgs
