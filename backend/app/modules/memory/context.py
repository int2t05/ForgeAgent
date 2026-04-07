"""LLM 上下文窗口管理：消息加载、Token 计数、预算截断、对话摘要。

核心能力：
  - 会话上下文：消息列表转 LangChain 格式、历史装填
  - 上下文预算：token 估算、超限截断、错误识别
  - 对话摘要：超长会话的 LLM 压缩
  - Token 计数：tiktoken 本地精确计数

使用场景：
  - Planner 加载会话历史作为规划上下文
  - ReAct 循环组装消息列表时应用预算截断

使用方式（按需导入以避免循环依赖）：
  from app.modules.memory.context import SessionLLMContextManager, estimate_messages_tokens, truncate_chat_messages_to_budget
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import tiktoken
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.models.message import Message
from app.repositories import message_repository
from app.shared.langchain_content import message_content_text

logger = logging.getLogger(__name__)

# ============================================================================
# Token Counting (from token_counter.py)
# ============================================================================

# gpt-4o / gpt-3.5 等对话格式每条消息的固定开销（与 OpenAI cookbook 常见写法一致）
_TOKENS_PER_MESSAGE = 4
_REPLY_PRIMING_TOKENS = 3


def _role_for_message(msg: BaseMessage) -> str:
    """映射为 OpenAI Chat API 的 role 字符串（仅用于编码长度，不影响计数公式）。"""
    if isinstance(msg, SystemMessage):
        return "system"
    if isinstance(msg, AIMessage):
        return "assistant"
    return "user"


def encoding_for_chat_model(model: str | None) -> tiktoken.Encoding:
    """按模型名选择编码；未知模型回退 cl100k_base。"""
    name = (model or "").strip()
    if not name:
        return tiktoken.get_encoding("cl100k_base")
    try:
        return tiktoken.encoding_for_model(name)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_messages_tokens(messages: list[BaseMessage], *, model: str | None) -> int:
    """使用 tiktoken 估算消息列表在对话格式下的 token 总数。"""
    enc = encoding_for_chat_model(model)
    total = 0
    for msg in messages:
        total += _TOKENS_PER_MESSAGE
        role = _role_for_message(msg)
        total += len(enc.encode(role))
        total += len(enc.encode(message_content_text(msg.content)))
    total += _REPLY_PRIMING_TOKENS
    return total


# ============================================================================
# Conversation Summary (from conversation_summary.py)
# ============================================================================


def _clip_summary_text(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


async def maybe_compress_chat_history(
    messages: list[BaseMessage],
    settings: Settings,
) -> list[BaseMessage]:
    """当条数超过阈值且已配置 LLM 时，将较早消息压成一条摘要 HumanMessage + 保留最近 ``keep_recent`` 条。"""
    if not settings.session_conversation_summary_enabled:
        return messages
    thr = int(settings.session_summarize_when_over)
    if len(messages) <= thr:
        return messages
    if not is_llm_configured(settings):
        return messages

    keep_n = min(int(settings.session_summary_keep_recent), len(messages) - 1)
    if keep_n < 1:
        return messages

    old = messages[:-keep_n]
    recent = messages[-keep_n:]

    line_cap = max(80, int(settings.session_summary_line_max_chars))
    lines: list[str] = []
    for m in old:
        role = getattr(m, "type", None) or "message"
        snippet = message_content_text(m.content)[:line_cap]
        lines.append(f"{role}: {snippet}")

    ans_cap = max(64, int(settings.session_summary_max_answer_chars))
    body = "\n".join(lines)
    prompt = (
        f"请用不超过 {ans_cap} 字的中文概括要点（用户目标、关键事实、已确认结论），勿编造、勿列提纲：\n\n"
        f"{body}"
    )

    chat = build_chat_model(settings)
    try:
        resp = await ainvoke_with_retry(chat, [HumanMessage(content=prompt)], settings)
    except Exception:
        logger.warning("会话历史摘要调用失败，回退为未压缩的完整消息列表", exc_info=True)
        return messages

    raw = getattr(resp, "content", None)
    summary = raw if isinstance(raw, str) else str(raw or "")
    summary = _clip_summary_text(summary, ans_cap + 24)
    if not summary:
        return messages

    head = HumanMessage(content=f"[历史对话摘要]\n{summary}")
    return [head, *recent]


# ============================================================================
# Session Context Manager (from session_context.py)
# ============================================================================

# 与 LangChain / OpenAI 习惯角色对齐（MessageCreate 允许任意 role，未知则降级为 HumanMessage）
_ROLE_MAP: dict[str, type[HumanMessage | AIMessage | SystemMessage]] = {
    "user": HumanMessage,
    "human": HumanMessage,
    "assistant": AIMessage,
    "ai": AIMessage,
}


def session_messages_to_chat_messages(rows: Sequence[Message]) -> list[BaseMessage]:
    """将 ORM ``Message`` 行转为 ``langchain_core.messages``（规划等多轮调用使用）。"""
    out: list[BaseMessage] = []
    for row in rows:
        role = (row.role or "").strip().lower()
        # 1. 规划/ReAct 节点已注入 SystemMessage，与供应商「单 system」习惯对齐
        # 2. 会话里若存 system 角色，改写为 HumanMessage 前缀，避免多条 SystemMessage
        if role == "system":
            out.append(
                HumanMessage(
                    content=f"[会话 system]\n{row.content}",
                )
            )
            continue
        cls = _ROLE_MAP.get(role, HumanMessage)
        out.append(cls(content=row.content))
    return out


class SessionLLMContextManager:
    """在配置的消息条数上限内，从 DB 加载会话窗口并转为 LangChain ``BaseMessage`` 列表。"""

    def __init__(self, max_messages: int) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        self._max_messages = max_messages

    async def load_chat_messages(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        fallback_user_content: str,
        settings: Settings | None = None,
    ) -> list[BaseMessage]:
        """加载会话最近 ``max_messages`` 条（按 id 时间序），无记录时用单条用户消息兜底；超长时可选摘要压缩。"""
        s = settings or get_settings()
        rows = await message_repository.list_recent_messages(
            db, session_id, limit=self._max_messages
        )
        if not rows:
            return [HumanMessage(content=fallback_user_content)]
        msgs = session_messages_to_chat_messages(rows)
        return await maybe_compress_chat_history(msgs, s)


# ============================================================================
# LLM Context Budget (from llm_context_budget.py)
# ============================================================================

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
        out: list[BaseMessage] = sys_list  # type: ignore
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
