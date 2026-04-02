"""执行域：流式助手总结回复。

将用户问题、计划步骤与工具执行轨迹拼入提示，经 OpenAI 兼容接口流式生成，
并按 thinking / answer 相位拆分输出（供节点与时间线消费）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import astream_with_retry
from app.modules.prompts.assistant_reply import ASSISTANT_EXECUTOR_SUMMARY_SYSTEM
from app.modules.execution.stream_split import ThinkAnswerStream

logger = logging.getLogger(__name__)


def _chunk_text_content(chunk: Any) -> str:
    """从流式 chunk 中提取可拼接的纯文本内容。"""
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
    plan_steps: list[dict[str, Any]],
    settings: Settings | None = None,
    *,
    tool_trace: list[dict[str, Any]] | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """产出 thinking / answer 相位的异步字符流（基于用户问题、计划与工具轨迹）。"""
    # 1. 组装 System / Human 提示与时间线分隔器
    s = settings or get_settings()
    splitter = ThinkAnswerStream()
    plan_text = json.dumps(plan_steps, ensure_ascii=False)
    trace_text = json.dumps(tool_trace, ensure_ascii=False) if tool_trace else "[]"
    sys_stream = ASSISTANT_EXECUTOR_SUMMARY_SYSTEM
    human_stream = (
        f"用户问题：{user_message}\n"
        f"计划步骤：{plan_text}\n"
        f"工具执行结果（JSON 数组，按步骤顺序）：{trace_text}"
    )
    # 2. 未配置模型时输出内置占位说明流
    if not is_llm_configured(s):
        ans = "任务已完成。配置 API Key 后可使用完整模型。\n"
        for i in range(0, len(ans), 4):
            for phase, delta in splitter.feed(ans[i : i + 4]):
                yield phase, delta
        for phase, delta in splitter.finalize():
            yield phase, delta
        return

    # 3. 经 LLM 流式生成并拆分为相位输出
    chat = build_chat_model(s)
    try:
        async for chunk in astream_with_retry(
            chat,
            [SystemMessage(content=sys_stream), HumanMessage(content=human_stream)],
            s,
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
