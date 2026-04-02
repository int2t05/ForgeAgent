"""llm_context_budget：裁剪与估算行为单测。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_context_budget import (
    estimate_messages_tokens,
    truncate_chat_messages_to_budget,
)


def test_estimate_heuristic_without_chat() -> None:
    m = [HumanMessage(content="abc" * 10)]
    n = estimate_messages_tokens(None, m)
    assert n >= 10


def test_truncate_keeps_system_and_shrinks_list() -> None:
    sys = SystemMessage(content="system prompt")
    body = [HumanMessage(content="h" * 2000) for _ in range(6)]
    msgs = [sys, *body]
    before = len(msgs)
    out = truncate_chat_messages_to_budget(None, msgs, max_input_tokens=400)
    assert isinstance(out[0], SystemMessage)
    assert len(out) < before
