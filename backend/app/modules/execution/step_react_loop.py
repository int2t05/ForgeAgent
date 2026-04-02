"""单计划步内的 ReAct：每轮模型可输出一批工具顺序执行，写入 Observation 后再进入下一轮直至 final_answer。

供 Actor 按步调用；与 ``tool_runner`` 事件语义一致。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.execution.tool_runner import run_single_tool_with_retry
from app.modules.prompts.step_react import build_step_react_system_prompt
from app.repositories import event_repository
from app.schemas.tools import ToolItem
from app.modules.memory.tool_observation_compact import (
    compact_json_for_prompt,
    observation_json_for_llm,
)
from app.shared.react_llm_output import (
    extract_tool_invocations,
    parse_react_round_json,
    pick_final_answer,
    pick_thought,
)

logger = logging.getLogger(__name__)

_PRIOR_TAIL = 4
# 无 tiktoken 时的粗略估算（约 4 字符 / token，仅用于单步预算护栏）
_CHARS_PER_TOKEN_EST: int = 4

# 工具均已成功但主循环未得到 final_answer 时，追加一轮仅收官用的用户提示（禁止再发工具字段）
_CLOSING_FINAL_NUDGE_ZH = (
    "系统提示：当前步骤里已执行的工具均返回成功（见上文 Observation）。\n"
    "请**仅**回复一个 JSON 对象，且**不要**包含 action、actions、tool_calls、calls。\n"
    '必须含 final_answer，示例：{"thought":"一句话","final_answer":"给用户看的本步结论（可概括工具输出要点）"}'
)


def _estimate_tokens(text: str) -> int:
    """按字符量粗估本轮输出占用 token，供单步预算阈值使用。"""
    if not (text and text.strip()):
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN_EST)


def _tail_prior(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """截取步前工具轨迹尾部，控制首轮上下文长度。"""
    if len(trace) <= _PRIOR_TAIL:
        return trace
    return trace[-_PRIOR_TAIL:]


def _msg_text(msg: Any) -> str:
    """从 Chat 消息对象取出纯文本 ``content``。"""
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    return str(content or "")


async def _try_react_closing_final_answer(
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
    # 1. 超单步 token 估算则不再追加调用
    if token_budget > 0 and total_tokens_used >= token_budget:
        return None, None, total_tokens_used
    messages.append(HumanMessage(content=_CLOSING_FINAL_NUDGE_ZH))
    try:
        msg = await ainvoke_with_retry(chat, messages, s)
    except Exception:
        logger.exception(
            "react closing final LLM invoke failed task=%s step=%s",
            task_id,
            step_id,
        )
        return None, None, total_tokens_used
    text = _msg_text(msg)
    used = total_tokens_used + _estimate_tokens(text)
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


def _synthetic_final_when_tools_ok(call_results: list[dict[str, Any]]) -> str:
    """工具全部成功但模型仍未给出终答时的固定摘要，避免本子步被标为失败。"""
    # 1. 汇总已成功调用的工具名，便于用户对照时间线
    names: list[str] = []
    for c in call_results:
        if not isinstance(c, dict):
            continue
        t = c.get("tool")
        if isinstance(t, str) and t.strip():
            names.append(t.strip())
    suffix = "、".join(names) if names else "（工具）"
    return f"本步已执行工具：{suffix}，均已成功；详细输出见任务时间线中的工具结果。"


def _observation_block(
    tool_name: str,
    last_exec: dict[str, Any],
    *,
    max_json_chars: int,
) -> str:
    """将单次工具执行结果序列化为 Observation 载荷（长度受控，避免大返回挤尽上下文）。"""
    return observation_json_for_llm(
        tool_name,
        last_exec,
        max_json_chars=max_json_chars,
    )


async def run_step_react_loop(
    task_id: str,
    step_id: Any,
    step: dict[str, Any],
    *,
    user_message: str,
    prior_tool_trace: list[dict[str, Any]],
    tools: list[ToolItem],
    settings: Settings | None = None,
    max_tool_tries: int,
    max_rounds: int,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """在单步轮次上限内运行 ReAct；每轮先执行模型给出的工具列表（可多个），再读 Observation 直至产出终答。"""
    s = settings or get_settings()
    # 1. 无可执行工具或模型未配置
    if not tools or not is_llm_configured(s):
        return False, [], None

    obs_cap = int(s.react_tool_observation_max_json_chars)

    # 2. 首轮消息（系统提示 + 用户任务 / 步骤 / 历史轨迹摘要）
    chat = build_chat_model(s)
    sys_text = build_step_react_system_prompt(tools)
    trace_snippet = compact_json_for_prompt(_tail_prior(prior_tool_trace), obs_cap)
    initial = (
        f"用户任务：{user_message}\n"
        f"当前步骤（仅目标）：{json.dumps(step, ensure_ascii=False)}\n"
        f"此前步骤轨迹摘要：{trace_snippet}\n"
        "输出本轮 JSON：thought +（actions 批量或单 action，或 final_answer）。"
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=sys_text),
        HumanMessage(content=initial),
    ]

    call_results: list[dict[str, Any]] = []
    step_final: str | None = None
    closing_thought: str | None = None
    rounds = max(1, int(max_rounds))
    round_num = 0
    token_budget = int(s.react_max_tokens_per_step)
    total_tokens_used = 0

    # 3. 步内循环：模型轮次 → 若有一批工具则顺序执行并回注 Observation → 否则收终答
    while True:
        if round_num >= rounds:
            logger.warning(
                "step react 达到轮次上限 task=%s step=%s max_rounds=%s",
                task_id,
                step_id,
                rounds,
            )
            break
        round_num += 1
        # 3.1 本步单轮：调用模型并解析 ReAct JSON
        try:
            msg = await ainvoke_with_retry(chat, messages, s)
        except Exception:
            logger.exception("step react LLM invoke failed task=%s step=%s", task_id, step_id)
            break

        text = _msg_text(msg)
        total_tokens_used += _estimate_tokens(text)
        if token_budget > 0 and total_tokens_used > token_budget:
            logger.warning(
                "step react 单步 token 估算超预算 task=%s step=%s used≈%s budget=%s",
                task_id,
                step_id,
                total_tokens_used,
                token_budget,
            )
            messages.append(AIMessage(content=text))
            break
        messages.append(AIMessage(content=text))
        data = parse_react_round_json(text)
        if not data:
            logger.warning("step react parse failed task=%s step=%s", task_id, step_id)
            break

        invocations = extract_tool_invocations(data)
        fa = pick_final_answer(data)
        thought_round = pick_thought(data)

        # 3.2 本轮若有工具调用（含批量）：顺序执行，每条 Observation 追加；终答留待下一轮结合结果输出
        if invocations:
            for tn, args in invocations:
                final_ok, last_exec, attempt_rows = await run_single_tool_with_retry(
                    task_id,
                    step_id,
                    tn,
                    args,
                    max_tool_tries,
                    react_thought=thought_round,
                )
                call_results.append(
                    {
                        "tool": tn,
                        "args": args,
                        "ok": final_ok,
                        "data": last_exec.get("data"),
                        "error": last_exec.get("error"),
                        "attempts": attempt_rows,
                    }
                )
                messages.append(
                    HumanMessage(
                        content="Observation:\n"
                        + _observation_block(tn, last_exec, max_json_chars=obs_cap),
                    )
                )
            continue

        # 3.3 无工具：仅终答则结束本步
        if fa:
            step_final = fa
            closing_thought = thought_round
            break

            break

    # 4. 本步整体成功与否：存在终答且历次工具均成功（无调用则视为真）
    all_tool_ok = all(c.get("ok") for c in call_results) if call_results else True

    # 4.1 工具已成功但主循环未收官：追加一轮「仅 final_answer」提示；仍无则写入诚实兜底终答
    if (
        not step_final
        and call_results
        and all_tool_ok
        and is_llm_configured(s)
    ):
        fa2, th2, total_tokens_used = await _try_react_closing_final_answer(
            chat,
            messages,
            s,
            task_id=task_id,
            step_id=step_id,
            token_budget=token_budget,
            total_tokens_used=total_tokens_used,
        )
        if fa2:
            step_final = fa2
            closing_thought = th2
        else:
            logger.warning(
                "react synthetic final after failed closing task=%s step=%s",
                task_id,
                step_id,
            )
            step_final = _synthetic_final_when_tools_ok(call_results)
            closing_thought = closing_thought or th2

    overall = bool(step_final) and all_tool_ok

    if step_final:
        try:
            payload_obj: dict[str, Any] = {
                "step_id": str(step_id),
                "final_answer": step_final,
            }
            ct = closing_thought if (closing_thought and str(closing_thought).strip()) else None
            if ct:
                payload_obj["thought"] = str(ct).strip()
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "react_turn",
                        json.dumps(payload_obj, ensure_ascii=False),
                    )
        except Exception:
            logger.exception(
                "append react_turn failed task=%s step=%s",
                task_id,
                step_id,
            )

    return overall, call_results, step_final
