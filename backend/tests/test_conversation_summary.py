"""conversation_summary：超长会话摘要与回退路径。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import Settings
from app.modules.memory.conversation_summary import maybe_compress_chat_history


@pytest.mark.asyncio
async def test_compress_skips_when_under_threshold() -> None:
    s = Settings(
        openai_api_key="sk-test",
        session_summarize_when_over=100,
        session_summary_keep_recent=10,
    )
    msgs = [HumanMessage(content="only")]
    out = await maybe_compress_chat_history(msgs, s)
    assert out is msgs


@pytest.mark.asyncio
async def test_compress_skips_without_llm_key() -> None:
    s = Settings(
        openai_api_key="",
        session_summarize_when_over=5,
        session_summary_keep_recent=2,
    )
    msgs = [HumanMessage(content=f"x{i}") for i in range(8)]
    out = await maybe_compress_chat_history(msgs, s)
    assert len(out) == 8


@pytest.mark.asyncio
async def test_compress_skips_when_disabled() -> None:
    s = Settings(
        openai_api_key="sk-test",
        session_conversation_summary_enabled=False,
        session_summarize_when_over=5,
        session_summary_keep_recent=2,
    )
    msgs = [HumanMessage(content=f"x{i}") for i in range(8)]
    out = await maybe_compress_chat_history(msgs, s)
    assert len(out) == 8


@pytest.mark.asyncio
async def test_compress_prepends_summary_and_keeps_recent() -> None:
    s = Settings(
        openai_api_key="sk-test",
        openai_model="gpt-4o-mini",
        session_summarize_when_over=10,
        session_summary_keep_recent=3,
    )
    msgs = [HumanMessage(content=f"m{i}") for i in range(12)]
    fake = AIMessage(content="短摘要一条")
    with patch(
        "app.core.llm_retry.ainvoke_with_retry",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = await maybe_compress_chat_history(msgs, s)
    assert len(out) == 4
    assert "短摘要一条" in str(out[0].content)
    assert out[-1].content == "m11"
    assert out[-2].content == "m10"
