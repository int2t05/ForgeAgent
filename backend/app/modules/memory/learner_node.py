"""Learn 模块：总结归纳 → 反思 → 判断重规划 or 生成最终回答。

核心职责：
1. 根据 Act 收集的上下文进行总结归纳
2. 反思执行结果
3. 判断是否需要重规划
4. 如果不需要重规划，生成最终回答
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.memory.session_blackboard import cap_blackboard_notes
from app.modules.prompts import LEARN_REFLECTION_SYSTEM, RETRY_LEARN
from app.modules.workflow.state import AgentState
from app.repositories import event_repository
from app.shared.langchain_content import message_content_text
from app.shared.llm_json_parse import parse_llm_json_object

logger = logging.getLogger(__name__)

_TK_O = "\u003cthink\u003e"
_TK_C = "\u003c/think\u003e"


def _build_learn_user_payload(state: AgentState) -> str:
    """构建 Learn 模块的用户输入。"""
    user_message = state.get("user_message") or ""
    plan_steps = state.get("plan_steps") or []
    act_context = state.get("act_context") or {}
    step_results = act_context.get("step_results") or []
    tool_trace = act_context.get("tool_trace") or []

    lines = [
        "## 用户任务",
        user_message,
        "",
        "## 计划步骤",
    ]

    for idx, step in enumerate(plan_steps):
        step_title = step.get("title") or f"步骤 {idx + 1}"
        lines.append(f"{idx + 1}. {step_title}")

    lines.append("")
    lines.append("## 执行结果")

    for result in step_results:
        step_id = result.get("step_id", "")
        title = result.get("title", "")
        ok = result.get("ok", False)
        status = "✓ 成功" if ok else "✗ 失败"
        lines.append(f"\n### {step_id}: {title} [{status}]")

        calls = result.get("calls", [])
        if calls:
            for call in calls:
                tool_name = call.get("tool", "unknown")
                call_ok = call.get("ok", False)
                call_status = "✓" if call_ok else "✗"
                error = call.get("error")
                if error:
                    lines.append(f"  - {call_status} {tool_name}: {error[:100]}")
                else:
                    lines.append(f"  - {call_status} {tool_name}")

        sfa = result.get("step_final_answer")
        if sfa:
            lines.append(f"  终答: {sfa[:200]}")

    return "\n".join(lines)


async def learn_node(state: AgentState) -> dict[str, Any]:
    """Learn 节点：总结归纳 → 反思 → 判断重规划 or 生成最终回答。"""
    task_id = state["task_id"] # type: ignore
    settings = get_settings()

    max_replan = max(0, int(state.get("max_replan_attempts") or 0))
    replan_count = int(state.get("replan_count") or 0)
    can_replan = replan_count < max_replan
    failed = state.get("outcome") == "failed"

    reflection_text = ""
    should_replan = False
    final_answer = ""

    if is_llm_configured(settings) and not failed:
        chat = build_chat_model(settings)
        user_block = _build_learn_user_payload(state)
        messages: list[BaseMessage] = [
            SystemMessage(content=LEARN_REFLECTION_SYSTEM),
            HumanMessage(content=user_block),
        ]

        max_attempts = max(1, int(settings.learner_parse_max_attempts))
        for attempt in range(max_attempts):
            try:
                msg = await ainvoke_with_retry(chat, messages, settings)
            except Exception:
                logger.exception(
                    "Learn: LLM failed for task=%s attempt=%s/%s",
                    task_id,
                    attempt + 1,
                    max_attempts,
                )
                if attempt >= max_attempts - 1:
                    break
                continue

            text = message_content_text(msg)
            data = parse_llm_json_object(text)

            if data:
                r = data.get("reflection")
                if isinstance(r, str) and r.strip():
                    reflection_text = r.strip()

                sr = data.get("should_replan")
                if isinstance(sr, bool):
                    should_replan = sr
                elif sr in (1, "1", "true", "True", "yes"):
                    should_replan = True

                fa = data.get("final_answer")
                if isinstance(fa, str) and fa.strip():
                    final_answer = fa.strip()

                break

            logger.warning(
                "Learn: parse failed for task=%s attempt=%s/%s",
                task_id,
                attempt + 1,
                max_attempts,
            )
            if attempt < max_attempts - 1:
                messages.append(msg)
                messages.append(HumanMessage(content=RETRY_LEARN))

    if not reflection_text:
        reflection_text = _synthesize_fallback_reflection(state)

    if failed or not can_replan:
        should_replan = False

    if not final_answer and not should_replan:
        final_answer = _generate_fallback_answer(state)

    notes = list(state.get("blackboard_notes") or [])
    notes.append(reflection_text)
    notes = cap_blackboard_notes(notes, settings.session_blackboard_max_notes)

    payload = json.dumps(
        {
            "reflection": reflection_text[:8000],
            "should_replan": should_replan,
            "final_answer": final_answer[:4000] if final_answer else None,
        },
        ensure_ascii=False,
    )

    async with get_db_session() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "memory",
                "reflection",
                payload,
            )

    if final_answer:
        answer_payload = json.dumps(
            {"content": final_answer},
            ensure_ascii=False,
        )
        async with get_db_session() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "execution",
                    "message",
                    answer_payload,
                )

    logger.info(
        "Learn: task=%s should_replan=%s reflection_len=%d",
        task_id,
        should_replan,
        len(reflection_text),
    )

    return {
        "learn_reflection": reflection_text,
        "learn_should_replan": should_replan,
        "learn_final_answer": final_answer,
        "blackboard_notes": notes,
        "replan_requested": should_replan,
        "summary": final_answer,
    }


def _synthesize_fallback_reflection(state: AgentState) -> str:
    """生成回退反思文本。"""
    act_context = state.get("act_context") or {}
    step_results = act_context.get("step_results") or []
    outcome = state.get("outcome")

    lines: list[str] = []

    if outcome == "failed":
        lines.append("执行过程中出现失败。")
    else:
        all_ok = all(r.get("ok", False) for r in step_results)
        if all_ok:
            lines.append("所有步骤执行成功。")
        else:
            lines.append("部分步骤执行失败。")

    for result in step_results:
        step_id = result.get("step_id", "")
        ok = result.get("ok", False)
        status = "成功" if ok else "失败"
        lines.append(f"步骤 {step_id}: {status}")

    return "\n".join(lines)


def _generate_fallback_answer(state: AgentState) -> str:
    """生成回退最终回答。"""
    act_context = state.get("act_context") or {}
    step_results = act_context.get("step_results") or []
    outcome = state.get("outcome")

    if outcome == "failed":
        return "任务执行过程中遇到问题，请检查后重试。"

    all_ok = all(r.get("ok", False) for r in step_results)
    if all_ok:
        return "任务已完成。"
    else:
        return "任务部分完成，部分步骤执行失败。"


def route_after_learn(state: AgentState) -> Literal["plan", "done"]:
    """Learn 之后的条件边路由。"""
    if state.get("outcome") == "failed":
        return "done"
    if state.get("replan_requested"):
        return "plan"
    return "done"


learner_node = learn_node
