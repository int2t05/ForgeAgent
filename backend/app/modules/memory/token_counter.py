"""OpenAI 兼容聊天消息的本地 token 计数（tiktoken），供上下文预算在无 Chat 模型实例时使用。"""

from __future__ import annotations

import tiktoken
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from app.shared.langchain_content import message_content_text

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
