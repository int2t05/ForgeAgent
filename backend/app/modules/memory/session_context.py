"""会话级上下文：持久化消息 ↔ LangChain ChatMessages（供规划 / 后续对话节点复用）。"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.repositories import message_repository

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
    ) -> list[BaseMessage]:
        """加载会话最近 ``max_messages`` 条（按 id 时间序），无记录时用单条用户消息兜底。"""
        rows = await message_repository.list_recent_messages(
            db, session_id, limit=self._max_messages
        )
        if not rows:
            return [HumanMessage(content=fallback_user_content)]
        return session_messages_to_chat_messages(rows)
