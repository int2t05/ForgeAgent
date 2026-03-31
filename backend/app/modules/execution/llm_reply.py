"""OpenAI 兼容流式助手回复（执行阶段汇总答案）。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.modules.execution.stream_split import ThinkAnswerStream

logger = logging.getLogger(__name__)


def _chunk_text_content(chunk: Any) -> str:
    content = getattr(chunk, "content", None)
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


async def assistant_reply_stream_with_llm(
    user_message: str,
    plan_steps: list[dict[str, str]],
    settings: Settings | None = None,
) -> AsyncIterator[tuple[str, str]]:
    s = settings or get_settings()
    splitter = ThinkAnswerStream()
    plan_text = json.dumps(plan_steps, ensure_ascii=False)
    sys_stream = "你是 ForgeAgent 助手。结合用户问题与下列计划，用中文直接回答。"
    human_stream = f"用户问题：{user_message}\n计划步骤：{plan_text}"

    if not is_llm_configured(s):
        ans = "任务已完成（LangGraph 最小闭环）。配置 API Key 后可使用完整模型。\n"
        for i in range(0, len(ans), 4):
            for phase, delta in splitter.feed(ans[i : i + 4]):
                yield phase, delta
        for phase, delta in splitter.finalize():
            yield phase, delta
        return

    chat = build_chat_model(s)
    try:
        async for chunk in chat.astream(
            [SystemMessage(content=sys_stream), HumanMessage(content=human_stream)]
        ):
            text = _chunk_text_content(chunk)
            if not text:
                continue
            for phase, delta in splitter.feed(text):
                yield phase, delta
        for phase, delta in splitter.finalize():
            yield phase, delta
    except Exception:
        logger.exception("assistant LLM stream failed")
        for phase, delta in splitter.finalize():
            yield phase, delta
