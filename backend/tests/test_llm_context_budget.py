"""llm_context_budget：裁剪与估算行为单测。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.memory.llm_context_budget import (
    estimate_messages_tokens,
    truncate_chat_messages_to_budget,
)


def test_estimate_exact_without_chat() -> None:
    m = [HumanMessage(content="abc" * 10)]
    n = estimate_messages_tokens(None, m)
    assert n >= 10


def test_truncate_keeps_system_and_prefers_recent() -> None:
    sys = SystemMessage(content="system prompt")
    body = [HumanMessage(content="h" * 2000) for _ in range(6)]
    msgs = [sys, *body]
    before = len(msgs)
    out = truncate_chat_messages_to_budget(None, msgs, max_input_tokens=400)
    assert isinstance(out[0], SystemMessage)
    assert len(out) < before
    assert isinstance(out[-1], HumanMessage)


def test_truncate_drops_oldest_human_first() -> None:
    sys = SystemMessage(content="s")
    old = HumanMessage(content="OLD-" + "x" * 6000)
    mid = HumanMessage(content="MID-" + "y" * 6000)
    new = HumanMessage(content="NEW-tail")
    msgs = [sys, old, mid, new]
    out = truncate_chat_messages_to_budget(None, msgs, max_input_tokens=256)
    assert isinstance(out[0], SystemMessage)
    joined = " ".join(
        str(m.content) for m in out if not isinstance(m, SystemMessage)
    )
    assert "OLD-" not in joined
    assert "NEW-tail" in joined
