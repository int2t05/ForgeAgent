"""单计划步内的 ReAct：每轮模型可输出一批工具顺序执行，写入 Observation 后再进入下一轮直至 final_answer。

供 Actor 按步调用；与 ``tool_runner`` 事件语义一致。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.execution.step_react_internals import (
    estimate_react_output_tokens,
    observation_block_for_llm,
    tail_prior_tool_trace,
    try_react_closing_final_answer,
)
from app.modules.execution.tool_runner import run_single_tool_with_retry
from app.modules.memory.tool_observation_compact import compact_json_for_prompt
from app.modules.prompts.parse_retry import REACT_PARSE_RETRY
from app.modules.prompts.react_hints import _SKILL_IMPORT_HUMAN_PREFIX
from app.modules.prompts.step_react import build_step_react_system_prompt
from app.repositories import event_repository
from app.schemas.tools import ToolItem
from app.shared.langchain_content import message_content_text
from app.shared.react_llm_output import (
    _FINAL_ANSWER_TRUE,
    extract_tool_invocations,
    parse_react_round_json,
    pick_final_answer,
    pick_thought,
)

logger = logging.getLogger(__name__)

# 限制工具并发执行数，避免连接池耗尽
_TOOL_SEMAPHORE = asyncio.Semaphore(3)


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
    skill_import_text: str = "",
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """在单步轮次上限内运行 ReAct；每轮先执行模型给出的工具列表（可多个），再读 Observation 直至产出终答。"""
    s = settings or get_settings()
    # 无可执行工具或模型未配置
    if not tools or not is_llm_configured(s):
        return False, [], None

    obs_cap = int(s.react_tool_observation_max_json_chars)

    # 首轮消息（系统提示 + 用户任务 / 步骤 / 历史轨迹摘要）
    chat = build_chat_model(s)
    sys_text = build_step_react_system_prompt(tools)
    trace_snippet = compact_json_for_prompt(
        tail_prior_tool_trace(prior_tool_trace),
        obs_cap,
    )
    initial = (
        f"User task: {user_message}\n"
        f"Current plan step (goal-level only): {json.dumps(step, ensure_ascii=False)}\n"
        f"Prior steps trace summary: {trace_snippet}\n"
        "Respond with JSON for this round: thought, then either batched actions, a single action, or final_answer."
    )
    messages: list[BaseMessage] = [SystemMessage(content=sys_text)]
    skill_ctx = (skill_import_text or "").strip()
    if skill_ctx:
        messages.append(HumanMessage(content=_SKILL_IMPORT_HUMAN_PREFIX + skill_ctx))
    messages.append(HumanMessage(content=initial))

    call_results: list[dict[str, Any]] = []
    step_final: str | None = None
    closing_thought: str | None = None
    rounds = max(1, int(max_rounds))
    round_num = 0
    token_budget = int(s.react_max_tokens_per_step)
    total_tokens_used = 0
    react_parse_failures = 0
    max_parse_attempts = max(1, int(s.react_parse_max_attempts))

    # 步内循环：模型轮次 → 若有一批工具则顺序执行并回注 Observation → 否则收终答
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
        try:
            msg = await ainvoke_with_retry(chat, messages, s)
        except Exception:
            logger.exception("step react LLM invoke failed task=%s step=%s", task_id, step_id)
            break

        text = message_content_text(msg)
        total_tokens_used += estimate_react_output_tokens(text)
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
            react_parse_failures += 1
            logger.warning(
                "step react parse failed task=%s step=%s (attempt %s/%s)",
                task_id,
                step_id,
                react_parse_failures,
                max_parse_attempts,
            )
            if react_parse_failures < max_parse_attempts:
                messages.append(HumanMessage(content=REACT_PARSE_RETRY))
                continue
            break

        invocations = extract_tool_invocations(data)
        fa = pick_final_answer(data)
        thought_round = pick_thought(data)

        if invocations:
            # 使用信号量限制并发执行，避免连接池耗尽
            async def run_with_semaphore(tn: str, args: dict[str, Any]) -> Any:
                async with _TOOL_SEMAPHORE:
                    return await run_single_tool_with_retry(
                        task_id,
                        step_id,
                        tn,
                        args,
                        max_tool_tries,
                        react_thought=thought_round,
                    )

            tasks = [run_with_semaphore(tn, args) for tn, args in invocations]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 按原顺序处理结果
            for (tn, args), result in zip(invocations, raw_results):
                if isinstance(result, Exception):
                    call_results.append(
                        {
                            "tool": tn,
                            "args": args,
                            "ok": False,
                            "data": None,
                            "error": str(result),
                            "attempts": [],
                        }
                    )
                    messages.append(
                        HumanMessage(
                            content="Observation:\n"
                            + observation_block_for_llm(
                                tn,
                                {"ok": False, "data": None, "error": str(result)},
                                max_json_chars=obs_cap,
                            ),
                        )
                    )
                else:
                    final_ok, last_exec, attempt_rows = result
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
                            + observation_block_for_llm(
                                tn,
                                last_exec,
                                max_json_chars=obs_cap,
                            ),
                        )
                    )
            continue

        if fa:
            # fa == _FINAL_ANSWER_TRUE 表示模型输出 final_answer:true，即"子目标满足可结束"
            # 此时 step_final 为哨兵（真值），跳过后续合成逻辑；break 后 overall=true
            step_final = fa
            closing_thought = thought_round
            break

    all_tool_ok = all(c.get("ok") for c in call_results) if call_results else True

    if (
        not step_final
        and call_results
        and all_tool_ok
        and is_llm_configured(s)
    ):
        fa2, th2, total_tokens_used = await try_react_closing_final_answer(
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
            step_final = _FINAL_ANSWER_TRUE
            closing_thought = closing_thought or th2

    overall = bool(step_final) and all_tool_ok

    if step_final:
        try:
            payload_obj: dict[str, Any] = {
                "step_id": str(step_id),
                "final_answer": True if step_final == _FINAL_ANSWER_TRUE else step_final,
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

    return overall, call_results, ("completed" if step_final == _FINAL_ANSWER_TRUE else step_final)
