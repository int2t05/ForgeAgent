"""LangChain 消息 content 扁平化为纯文本：供 token 计数、摘要、流式与 Observation 等多处复用。"""

from __future__ import annotations

from typing import Any


def message_content_text(content: Any) -> str:
    """将任意 content 扁平化为纯文本。

    支持 LangChain ``BaseMessage`` / 流式 chunk（自动取 ``.content``），
    也直接接受字符串或列表（多段文本块）。
    """
    if hasattr(content, "content"):
        content = getattr(content, "content")
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
