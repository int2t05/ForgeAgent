"""记忆域 LangGraph 节点（Learner）：对本回合 Actor 轨迹做反思，写入黑板并决定是否再进 Planner。

反思可由模型 JSON 或确定性摘要生成；与 ``session_blackboard`` 上限策略配合截断历史。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.memory.session_blackboard import cap_blackboard_notes
from app.modules.prompts.learner_reflection import (
    LEARNER_REFLECTION_SYSTEM,
    build_learner_reflection_user_payload,
)
from app.modules.prompts.parse_retry import LEARNER_PARSE_RETRY
from app.modules.workflow.state import AgentState
from app.repositories import event_repository
from app.shared.langchain_content import message_content_text
from app.shared.llm_json_parse import parse_llm_json_object

logger = logging.getLogger(__name__)


def _synthesize_lesson_lines(state: AgentState) -> list[str]:
    """由 ``actor_tool_trace`` 与任务终态生成面向黑板的短文行列表（模型不可用时的回退正文素材）。"""
    lines: list[str] = []
    trace: list[dict[str, Any]] = list(state.get("actor_tool_trace") or [])
    replan = bool(state.get("replan_requested"))
    outcome = state.get("outcome")

    if not trace and replan:
        lines.append("重规划请求：当前尚无工具轨迹，黑板记录供下一轮 Planner 调整。")
    for row in trace:
        sid = row.get("step_id")
        title = row.get("title") or ""
        if row.get("skipped_no_tool"):
            lines.append(f"步骤 {sid} ({title})：未声明工具，已跳过。")
            continue
        if row.get("react_loop"):
            sub = row.get("calls")
            if isinstance(sub, list):
                for c in sub:
                    if not isinstance(c, dict):
                        continue
                    tname = c.get("tool")
                    ok_c = c.get("ok")
                    err_c = c.get("error")
                    if ok_c:
                        lines.append(f"步骤 {sid} ({title})：工具 {tname} 调用成功。")
                    else:
                        es = (
                            err_c
                            if isinstance(err_c, str) and err_c.strip()
                            else "失败"
                        )
                        lines.append(f"步骤 {sid} ({title})：工具 {tname} 未成功 — {es}")
            fa = row.get("step_final_answer")
            if isinstance(fa, str) and fa.strip():
                st = fa.strip()
                if len(st) > 120:
                    lines.append(f"步骤 {sid} ({title})：子步终答 — {st[:120]}…")
                else:
                    lines.append(f"步骤 {sid} ({title})：子步终答 — {st}")
            elif not (isinstance(sub, list) and sub):
                lines.append(f"步骤 {sid} ({title})：ReAct 未正常结束。")
            continue
        sub = row.get("calls")
        if isinstance(sub, list) and sub:
            for c in sub:
                if not isinstance(c, dict):
                    continue
                tname = c.get("tool")
                ok_c = c.get("ok")
                err_c = c.get("error")
                if ok_c:
                    lines.append(f"步骤 {sid} ({title})：工具 {tname} 调用成功。")
                else:
                    es = (
                        err_c
                        if isinstance(err_c, str) and err_c.strip()
                        else "失败"
                    )
                    lines.append(f"步骤 {sid} ({title})：工具 {tname} 未成功 — {es}")
            continue
        tool = row.get("tool")
        ok = row.get("ok")
        err = row.get("error")
        if ok:
            lines.append(f"步骤 {sid} ({title})：工具 {tool} 调用成功。")
        else:
            err_s = err if isinstance(err, str) and err.strip() else "失败"
            lines.append(f"步骤 {sid} ({title})：工具 {tool} 未成功 — {err_s}")

    if outcome == "success" and trace:
        lines.append("本回合执行成功，终态摘要已由 Actor 写入。")
    elif outcome == "success" and not trace and not replan:
        lines.append("本回合无工具轨迹，Actor 已直接产出答复。")
    elif outcome == "failed":
        msg = state.get("error_message") or ""
        lines.append(f"本回合失败：{msg}" if msg else "本回合失败。")

    if replan and trace:
        lines.append("需重规划：请将上述工具结果与约束反映在更新后的步骤中。")

    return lines


async def learner_node(state: AgentState) -> dict[str, Any]:
    """追加黑板、写反思事件，并合并 Actor/模型意图得到 ``replan_requested``。"""
    task_id = state["task_id"]  # type: ignore
    settings = get_settings()
    # 1. 读取重规划上限、已重规划次数、Actor 再规划标志与失败标记
    max_r = max(0, int(state.get("max_replan_attempts") or 0))
    replan_count = int(state.get("replan_count") or 0)
    can_replan = replan_count < max_r
    failed = state.get("outcome") == "failed"
    actor_replan = bool(state.get("replan_requested"))

    fallback_lines = _synthesize_lesson_lines(state)
    reflection_text = ""
    llm_request_replan = False

    # 2. LLM 可用且本回合非失败：请求结构化反思 JSON（解析失败时可多轮纠偏重试）
    if is_llm_configured(settings) and not failed:
        chat = build_chat_model(settings)
        user_block = build_learner_reflection_user_payload(state)
        messages: list[BaseMessage] = [
            SystemMessage(content=LEARNER_REFLECTION_SYSTEM),
            HumanMessage(content="【本回合执行材料】\n" + user_block),
        ]
        max_rounds = max(1, int(settings.learner_parse_max_attempts))
        for attempt in range(max_rounds):
            try:
                msg = await ainvoke_with_retry(chat, messages, settings)
            except Exception:
                logger.exception(
                    "learner reflection LLM failed for task %s (attempt %s/%s)",
                    task_id,
                    attempt + 1,
                    max_rounds,
                )
                if attempt >= max_rounds - 1:
                    break
                continue

            text = message_content_text(msg)
            data = parse_llm_json_object(text)
            parsed_ok = False
            if data:
                r = data.get("reflection")
                if isinstance(r, str) and r.strip():
                    reflection_text = r.strip()
                    raw_rp = data.get("request_replan")
                    if isinstance(raw_rp, bool):
                        llm_request_replan = raw_rp
                    elif raw_rp in (1, "1", "true", "True", "yes"):
                        llm_request_replan = True
                    parsed_ok = True
            if parsed_ok:
                break

            logger.warning(
                "learner reflection output not valid JSON or unusable reflection for task %s "
                "(attempt %s/%s)",
                task_id,
                attempt + 1,
                max_rounds,
            )
            if attempt < max_rounds - 1:
                messages.append(msg)
                messages.append(HumanMessage(content=LEARNER_PARSE_RETRY))

    # 3. 若无模型正文则用轨迹摘要拼接；失败或超限则清零模型再规划请求
    if not reflection_text and fallback_lines:
        reflection_text = "\n".join(fallback_lines)
    if not reflection_text:
        reflection_text = "（本回合无可写入黑板的要点）"

    if failed or not can_replan:
        llm_request_replan = False

    # 4. 在允许再规划且未失败时合并 Actor 与模型的再规划意图
    wants_replan = (not failed) and can_replan and (actor_replan or llm_request_replan)

    # 5. 截断黑板、写 ``memory/reflection``、清空本回合 ``actor_tool_trace`` 引用
    notes = list(state.get("blackboard_notes") or [])
    notes.append(reflection_text)
    notes = cap_blackboard_notes(notes, settings.session_blackboard_max_notes)

    payload = json.dumps(
        {
            "outcome": state.get("outcome"),
            "actor_replan_flag": actor_replan,
            "llm_request_replan": llm_request_replan,
            "effective_replan": wants_replan,
            "reflection": reflection_text[:8000],
        },
        ensure_ascii=False,
    )
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "memory",
                "reflection",
                payload,
            )

    return {
        "blackboard_notes": notes,
        "actor_tool_trace": [],
        "replan_requested": wants_replan,
    }
