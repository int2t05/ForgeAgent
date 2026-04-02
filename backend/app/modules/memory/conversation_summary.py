"""会话历史摘要压缩：超长时由 LLM 生成短摘要替换较早消息，保留最近若干条原文。"""

from __future__ import annotations

import logging

from langchain_core.messages import BaseMessage, HumanMessage

from app.core.config import Settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.shared.langchain_content import message_content_text

logger = logging.getLogger(__name__)


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

    from app.core.llm_retry import ainvoke_with_retry

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
