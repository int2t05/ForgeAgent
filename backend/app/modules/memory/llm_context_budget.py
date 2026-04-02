"""LLM 输入侧上下文预算与截断。

依据应用配置的输入 token 上限裁剪 Chat 历史：系统消息整体上保留在序列前部（超预算时可
删减较早系统段或截断单条），非系统消息自最新向最旧贪心装入。供 ``llm_retry``、规划层等
在调用模型前统一收敛 prompt 体积。

计数优先使用 Chat 模型的 ``get_num_tokens_from_messages``，其次 tiktoken，失败则启发式。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings
from app.modules.memory.token_counter import count_messages_tokens
from app.shared.langchain_content import message_content_text

logger = logging.getLogger(__name__)

_TAIL_HINT = "\n\n[... 已省略部分内容以适配上下文窗口 ...]"

_TRUNCATION_LOG_MSG = (
    "LLM 上下文已裁剪：估算约 %s → %s tokens。"
    "应用层输入截断上限 %s tokens（窗口 %s − 预留输出 %s）。"
    "模型/API 总上下文窗口 %s tokens（prompt 与补全共用；历史装填与截断仅按应用层输入上限）。"
)


def _log_context_truncated(before: int, after: int, budget: int) -> None:
    """输出裁剪结果告警：对比裁剪前后 token 估算并附带窗口配置说明。"""
    s = get_settings()
    win = int(s.llm_context_window_tokens)
    res = int(s.llm_reserved_completion_tokens)
    logger.warning(_TRUNCATION_LOG_MSG, before, after, budget, win, res, win)


def _model_name_for_token_count(chat: BaseChatModel | None) -> str | None:
    """解析 tiktoken 所用模型名：优先 Chat 实例，否则 OpenAI 配置项。"""
    if chat is not None:
        raw = getattr(chat, "model_name", None) or getattr(chat, "model", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    m = (get_settings().openai_model or "").strip()
    return m or None


def _heuristic_messages_tokens(msgs: list[BaseMessage]) -> int:
    """tiktoken 不可用时，以字符长度粗估 token（偏保守）。"""
    total = 0
    for m in msgs:
        total += max(1, len(message_content_text(m.content)) // 3)
    total += len(msgs) * 4
    return total


def estimate_messages_tokens(
    chat: BaseChatModel | None,
    messages: Sequence[BaseMessage],
) -> int:
    """估算消息列表 token 总数，在 Chat 内置、tiktoken 与启发式之间自动选用可用实现。"""
    msgs = list(messages)
    if chat is not None:
        getter = getattr(chat, "get_num_tokens_from_messages", None)
        if callable(getter):
            try:
                return int(getter(msgs))
            except Exception:
                pass
    if get_settings().llm_use_exact_token_count:
        try:
            return count_messages_tokens(msgs, model=_model_name_for_token_count(chat))
        except Exception:
            logger.debug("tiktoken 计数失败，回退启发式", exc_info=True)
    return _heuristic_messages_tokens(msgs)


def is_context_limit_error(exc: BaseException) -> bool:
    """判断异常文案是否像供应商返回的上下文或 token 长度限制。"""
    s = str(exc).lower()
    return (
        "context" in s
        and ("limit" in s or "exceed" in s or "exceeds" in s or "token" in s)
    ) or "maximum context" in s


def _clone_message(msg: BaseMessage, text: str) -> BaseMessage:
    """克隆一条同类型消息，仅替换正文为 ``text``。"""
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
    """将单条消息正文截断到不超过 ``max_tokens``（对长度二分）。"""
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


def _shrink_system_list(
    chat: BaseChatModel | None,
    sys_list: list[BaseMessage],
    budget: int,
    original_len: int,
) -> None:
    """就地压缩 ``sys_list``，使合计 token 不超过 ``budget``。"""
    guard = 0
    while sys_list and estimate_messages_tokens(chat, sys_list) > budget and guard < original_len + 4:
        guard += 1
        if len(sys_list) > 1:
            sys_list.pop(0)
            continue
        sys_list[0] = _truncate_one_message(chat, sys_list[0], budget)
        break


def _squeeze_to_budget(
    chat: BaseChatModel | None,
    out: list[BaseMessage],
    *,
    leading_systems: int,
    budget: int,
) -> None:
    """``out`` 仍超 ``budget`` 时，从索引 ``leading_systems`` 起丢最早非系统消息，否则截断末条。"""
    guard = 0
    while out and estimate_messages_tokens(chat, out) > budget and guard < 4096:
        guard += 1
        if len(out) > leading_systems:
            out.pop(leading_systems)
            continue
        out[-1] = _truncate_one_message(chat, out[-1], budget)


def truncate_chat_messages_to_budget(
    chat: BaseChatModel | None,
    messages: Sequence[BaseMessage],
    *,
    max_input_tokens: int,
) -> list[BaseMessage]:
    """将 ``messages`` 截断到不超过 ``max_input_tokens`` 的输入 token 估算值。"""
    budget = max(64, int(max_input_tokens))
    msgs = list(messages)
    before = estimate_messages_tokens(chat, msgs)
    if before <= budget:
        return msgs

    # 1. 拆分系统消息与其余角色消息
    raw_sys = [m for m in msgs if isinstance(m, SystemMessage)]
    others = [m for m in msgs if not isinstance(m, SystemMessage)]

    sys_list = list(raw_sys)
    # 2. 将系统块压入预算（可删前段或截断单条）
    _shrink_system_list(chat, sys_list, budget, len(raw_sys))
    n_sys = len(sys_list)

    # 3. 无非系统消息时只做末端挤压并打日志
    if not others:
        out: list[BaseMessage] = sys_list # type: ignore
        _squeeze_to_budget(chat, out, leading_systems=len(out), budget=budget)
        after = estimate_messages_tokens(chat, out)
        _log_context_truncated(before, after, budget)
        return out

    # 4. 自新向旧贪心装入非系统消息
    kept_rev: list[BaseMessage] = []
    for msg in reversed(others):
        trial = sys_list + list(reversed(kept_rev + [msg]))
        if estimate_messages_tokens(chat, trial) <= budget:
            kept_rev.append(msg)
        else:
            break

    # 5. 若连一条完整非系统消息都装不下，则为最后一条非系统消息单独留宽并截断
    if kept_rev:
        out = sys_list + list(reversed(kept_rev))
    else:
        room = max(32, budget - estimate_messages_tokens(chat, sys_list))
        out = sys_list + [_truncate_one_message(chat, others[-1], room)]

    # 6. 最终再挤压一轮，确保落在预算内并打日志
    _squeeze_to_budget(chat, out, leading_systems=n_sys, budget=budget)
    after = estimate_messages_tokens(chat, out)
    _log_context_truncated(before, after, budget)
    return out
