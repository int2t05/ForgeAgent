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
        # 规划节点单独注入 SystemMessage；会话内 system 易与供应商「单 system」约束冲突，改为Human侧说明
        # LLM 调用只能有一个 system prompt，多个 system 会冲突，所以把会话内的 system 内容包装成用户提示）
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
    """统一管理「从 DB 拉取最近窗口 + 转为 LLM 消息列表」；窗口大小由配置上限控制。

    与 LangChain 推荐用法一致：向 ``BaseChatModel.ainvoke`` 传入 ``list[BaseMessage]``。
    """

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
