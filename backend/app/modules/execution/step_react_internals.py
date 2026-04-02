"""单步 ReAct 内部 helpers：收口轮、Observation 文本与 token 粗估，供 ``step_react_loop`` 使用。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.core.config import Settings
from app.core.llm_retry import ainvoke_with_retry
from app.modules.memory.tool_observation_compact import observation_json_for_llm
from app.modules.prompts.react_hints import CLOSING_FINAL_NUDGE
from app.shared.langchain_content import message_content_text
from app.shared.react_llm_output import (
    extract_tool_invocations,
    parse_react_round_json,
    pick_final_answer,
    pick_thought,
)

logger = logging.getLogger(__name__)

PRIOR_TRACE_TAIL_LIMIT = 4
_CHARS_PER_TOKEN_EST = 4


def estimate_react_output_tokens(text: str) -> int:
    """按字符量粗估本轮输出占用 token，供单步预算阈值使用。"""
    if not (text and text.strip()):
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN_EST)


def tail_prior_tool_trace(
    trace: list[dict[str, Any]],
    *,
    limit: int = PRIOR_TRACE_TAIL_LIMIT,
) -> list[dict[str, Any]]:
    """截取步前工具轨迹尾部，控制首轮上下文长度。"""
    if len(trace) <= limit:
        return trace
    return trace[-limit:]


def observation_block_for_llm(
    tool_name: str,
    last_exec: dict[str, Any],
    *,
    max_json_chars: int,
) -> str:
    """将单次工具执行结果序列化为 Observation 载荷（长度受控）。"""
    return observation_json_for_llm(
        tool_name,
        last_exec,
        max_json_chars=max_json_chars,
    )


def synthetic_final_when_all_tools_ok(call_results: list[dict[str, Any]]) -> str:
    """工具全部成功但模型仍未给出终答时的固定摘要，避免本子步被标为失败。"""
    names: list[str] = []
    for c in call_results:
        if not isinstance(c, dict):
            continue
        t = c.get("tool")
        if isinstance(t, str) and t.strip():
            names.append(t.strip())
    suffix = "、".join(names) if names else "（工具）"
    return f"本步已执行工具：{suffix}，均已成功；详细输出见任务时间线中的工具结果。"


async def try_react_closing_final_answer(
    chat: Any,
    messages: list[BaseMessage],
    s: Settings,
    *,
    task_id: str,
    step_id: Any,
    token_budget: int,
    total_tokens_used: int,
) -> tuple[str | None, str | None, int]:
    """在工具已成功的前提下追加一轮模型调用，争取产出 final_answer。"""
    if token_budget > 0 and total_tokens_used >= token_budget:
        return None, None, total_tokens_used
    messages.append(HumanMessage(content=CLOSING_FINAL_NUDGE))
    try:
        msg = await ainvoke_with_retry(chat, messages, s)
    except Exception:
        logger.exception(
            "react closing final LLM invoke failed task=%s step=%s",
            task_id,
            step_id,
        )
        return None, None, total_tokens_used
    text = message_content_text(msg)
    used = total_tokens_used + estimate_react_output_tokens(text)
    messages.append(AIMessage(content=text))
    data = parse_react_round_json(text)
    if not data:
        logger.warning(
            "react closing final parse failed task=%s step=%s",
            task_id,
            step_id,
        )
        return None, None, used
    if extract_tool_invocations(data):
        logger.warning(
            "react closing final still emitted tools task=%s step=%s",
            task_id,
            step_id,
        )
    fa = pick_final_answer(data)
    th = pick_thought(data)
    if fa:
        return fa, th, used
    return None, th, used
