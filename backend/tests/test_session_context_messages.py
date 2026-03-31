"""会话消息 → LangChain BaseMessage 的映射单测。"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage

from app.models.message import Message
from app.modules.memory.session_context import session_messages_to_chat_messages


def _msg(session_id: str, role: str, content: str, mid: int) -> Message:
    m = Message(session_id=session_id, role=role, content=content)
    m.id = mid
    m.created_at = datetime.now(timezone.utc)
    return m


def test_maps_user_and_assistant() -> None:
    rows = [
        _msg("s1", "user", "你好", 1),
        _msg("s1", "assistant", "在的", 2),
        _msg("s1", "user", "再帮我规划 A", 3),
    ]
    lc = session_messages_to_chat_messages(rows)
    assert len(lc) == 3
    assert isinstance(lc[0], HumanMessage) and lc[0].content == "你好"
    assert isinstance(lc[1], AIMessage) and lc[1].content == "在的"
    assert isinstance(lc[2], HumanMessage) and lc[2].content == "再帮我规划 A"


def test_system_becomes_human_prefixed() -> None:
    rows = [_msg("s1", "system", "请用中文", 1)]
    lc = session_messages_to_chat_messages(rows)
    assert len(lc) == 1
    assert isinstance(lc[0], HumanMessage)
    assert "请用中文" in str(lc[0].content)
    assert "[会话 system]" in str(lc[0].content)
