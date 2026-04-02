"""LangChain消息 ``content`` 扁平化为纯文本：供 token 计数、摘要、流式与 Observation 等多处复用。"""

from __future__ import annotations

from typing import Any


def message_content_text(content: Any) -> str:
    """抽取消息体纯文本（字符串 / 多段文本块 / 其它类型降级为 ``str``）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def lc_message_text(message_like: Any) -> str:
    """从 LangChain ``BaseMessage`` / 流式 chunk 等对象取出扁平化纯文本。"""
    return message_content_text(getattr(message_like, "content", None))
