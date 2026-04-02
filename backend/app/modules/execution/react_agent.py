"""执行域：ReAct（推理-行动-观察）路径下的图节点实现。

与 plan_execute 分支并列；工具调用经统一注册表，事件形态与既有 execution/tool 事件对齐。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_context_budget import is_context_limit_error
from app.core.llm_retry import ainvoke_with_retry
from app.modules.memory.session_context import SessionLLMContextManager
from app.modules.execution.llm_reply import _chunk_text_content
from app.modules.execution.nodes import _StreamDeltaBatcher, _TK_C, _TK_O
from app.modules.prompts.catalog import tools_catalog_for_prompt
from app.modules.prompts.react import (
    REACT_JSON_PARSE_NUDGE,
    REACT_SHAPE_NUDGE,
    TOOL_FAILURE_NUDGE,
    build_react_system_prompt,
)
from app.modules.tools.registry import tool_registry
from app.modules.workflow.state import AgentState
from app.repositories import event_repository
from app.shared.react_llm_output import (
    parse_react_round_json,
    pick_action_input,
    pick_final_answer,
    pick_react_tool_name,
    pick_thought,
)

logger = logging.getLogger(__name__)


def _append_observation(
    messages: list[BaseMessage], observation: dict[str, Any]
) -> None:
    """向消息列表追加一条 HumanMessage 形式的 Observation。"""
    text = json.dumps(observation, ensure_ascii=False)
    messages.append(HumanMessage(content=f"Observation:\n{text}"))


async def _stream_react_round_deltas(
    task_id: str,
    step_id: str,
    *,
    thinking: str,
    tail_phase: Literal["answer", "action"],
    tail_text: str,
) -> None:
    """本回合思考与尾部阶段（用户可见答复或工具调用说明）分片写入 llm_stream_delta。"""
    batcher = _StreamDeltaBatcher(task_id, step_id)
    try:
        if tail_phase == "answer":
            step = max(30, len(tail_text) // 12)
            if thinking:
                for i in range(0, len(thinking), step):
                    await batcher.add("thinking", thinking[i : i + step])
            if tail_text:
                for i in range(0, len(tail_text), step):
                    await batcher.add("answer", tail_text[i : i + step])
        else:
            if thinking:
                t_step = max(30, len(thinking) // 12)
                for i in range(0, len(thinking), t_step):
                    await batcher.add("thinking", thinking[i : i + t_step])
            if tail_text:
                a_step = max(36, len(tail_text) // 14)
                for i in range(0, len(tail_text), a_step):
                    await batcher.add("action", tail_text[i : i + a_step])
    finally:
        await batcher.flush()


async def react_executor_node(state: AgentState) -> dict:
    """LangGraph ReAct 节点：多轮模型输出解析、工具调用或终答，受墙钟/停滞/轮次上限约束。"""
    # 1. 读取任务标识、会话、用户输入与循环约束
    task_id = state["task_id"]  # type: ignore
    session_id = state.get("session_id") or ""
    user_message = state.get("user_message") or ""
    settings = get_settings()
    max_rounds = max(1, int(getattr(settings, "max_react_iterations", 512) or 512))
    max_tool_fail = max(1, int(getattr(settings, "max_tool_failure_attempts", 3) or 3))
    wall_sec = max(60.0, float(getattr(settings, "react_agent_wall_timeout_sec", 1800.0) or 1800.0))
    stall_sec = max(30.0, float(getattr(settings, "react_agent_stall_timeout_sec", 180.0) or 180.0))
    # 2. 加载会话最近消息窗口
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        chat_messages = await mgr.load_chat_messages(
            db,
            session_id=session_id,
            fallback_user_content=user_message,
        )

    # 3. 拉取工具注册表目录与允许的 tool 名称集合
    tools = tool_registry.list_tools_public().tools
    catalog = tools_catalog_for_prompt(tools)
    tool_names = frozenset(t.name for t in tools)

    # 4. 未配置 LLM 时返回确定性成功摘要
    if not is_llm_configured(settings):
        summary = "任务已完成（LangGraph 最小闭环）。配置 API Key 后可使用 ReAct 与工具循环。\n"
        return {"outcome": "success", "summary": summary, "replan_requested": False}

    # 5. 初始化 ReAct 消息链与 Chat 客户端
    sys = build_react_system_prompt(catalog)
    messages: list[BaseMessage] = [SystemMessage(content=sys), *chat_messages]
    chat = build_chat_model(settings)
    tool_trace: list[dict[str, Any]] = []
    consecutive_tool_failures = 0
    loop_start = time.monotonic()
    last_progress_at = loop_start
    round_idx = 0

    async def _fail_loop(msg: str, *, reason: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "execution",
                    "error",
                    json.dumps({"message": msg, "reason": reason}, ensure_ascii=False),
                )
        return {
            "outcome": "failed",
            "error_message": msg,
            "summary": None,
            "replan_requested": False,
        }

    # 6. ReAct agent loop（每轮：墙钟/停滞/轮次检查 → 模型 → 解析 → 工具 / 终答 / 纠错）
    while True:
        round_idx += 1
        now = time.monotonic()
        if now - loop_start >= wall_sec:
            return await _fail_loop(
                f"ReAct 已超过墙钟上限（{int(wall_sec)} 秒）",
                reason="react_wall_timeout",
            )
        if now - last_progress_at >= stall_sec:
            return await _fail_loop(
                f"ReAct 已超过停滞阈值（{int(stall_sec)} 秒内无有效进展），可能卡住",
                reason="react_stall_timeout",
            )
        if round_idx > max_rounds:
            return await _fail_loop(
                f"ReAct 超过安全轮次上限（{max_rounds}）",
                reason="react_max_rounds",
            )

        try:
            reply = await ainvoke_with_retry(chat, messages, settings)
        except Exception as e:
            logger.exception("react LLM invoke failed at round %s", round_idx)
            fail_detail = f"ReAct 第 {round_idx} 轮模型调用失败"
            user_err = "ReAct 模型调用失败"
            if is_context_limit_error(e):
                user_err = (
                    "ReAct 模型调用失败：上下文超出供应商限制，请核对 LLM_CONTEXT_WINDOW_TOKENS、"
                    "LLM_RESERVED_COMPLETION_TOKENS 与 SESSION_MEMORY_MAX_MESSAGES"
                )
                fail_detail = f"{fail_detail}（上下文超限）"
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "error",
                        json.dumps(
                            {"message": fail_detail},
                            ensure_ascii=False,
                        ),
                    )
            return {
                "outcome": "failed",
                "error_message": user_err,
                "summary": None,
                "replan_requested": False,
            }

        text = _chunk_text_content(reply)
        messages.append(AIMessage(content=text))
        # 解析单轮 JSON；失败则 step_start 与 parse_error 后返回失败
        data = parse_react_round_json(text)
        round_title = f"ReAct 第 {round_idx} 轮"
        round_sid = f"react-{round_idx}"

        async def _emit_step_start(extra: dict[str, Any] | None = None) -> None:
            payload: dict[str, Any] = {
                "step_id": round_sid,
                "title": round_title,
            }
            if extra:
                payload.update(extra)
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_start",
                        json.dumps(payload, ensure_ascii=False),
                    )

        if not data:
            await _emit_step_start()
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {"step_id": round_sid, "status": "parse_error"},
                            ensure_ascii=False,
                        ),
                    )
            messages.append(HumanMessage(content=REACT_JSON_PARSE_NUDGE))
            continue

        last_progress_at = time.monotonic()
        thought_str = pick_thought(data)
        await _emit_step_start({"thought": thought_str} if thought_str else None)

        fa = pick_final_answer(data)
        action = pick_react_tool_name(data)

        # 存在 final_answer：落库 step_end、流式写入总结并成功返回
        if fa:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {"step_id": round_sid, "status": "final_answer"},
                            ensure_ascii=False,
                        ),
                    )
            tool_trace.append(
                {
                    "round": round_idx,
                    "thought": thought_str,
                    "final_answer": fa,
                }
            )
            full_t = thought_str or ""
            full_a = fa
            await _stream_react_round_deltas(
                task_id,
                round_sid,
                thinking=full_t,
                tail_phase="answer",
                tail_text=full_a,
            )
            if full_t.strip():
                summary = f"{_TK_O}{full_t.strip()}{_TK_C}\n\n{full_a}"
            else:
                summary = full_a
            return {
                "outcome": "success",
                "summary": summary,
                "replan_requested": False,
            }

        # 存在 action：校验工具名、落库 tool 事件、执行并拼接 Observation
        if action:
            name = action
            if name not in tool_names:
                err = f"ReAct 声明了未注册工具: {name}"
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        await event_repository.append_event(
                            db,
                            task_id,
                            "execution",
                            "error",
                            json.dumps({"message": err}, ensure_ascii=False),
                        )
                        await event_repository.append_event(
                            db,
                            task_id,
                            "execution",
                            "step_end",
                            json.dumps(
                                {"step_id": round_sid, "status": "unknown_tool"},
                                ensure_ascii=False,
                            ),
                        )
                return {
                    "outcome": "failed",
                    "error_message": err,
                    "summary": None,
                    "replan_requested": False,
                }
            args = pick_action_input(data)

            full_t = thought_str or ""
            action_text = (
                f"调用工具：{name}\n{json.dumps(args, ensure_ascii=False, indent=2)}"
            )
            await _stream_react_round_deltas(
                task_id,
                round_sid,
                thinking=full_t,
                tail_phase="action",
                tail_text=action_text,
            )

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_call",
                        json.dumps(
                            {
                                "step_id": round_sid,
                                "tool": name,
                                "args": args,
                            },
                            ensure_ascii=False,
                        ),
                    )
            exec_out = await tool_registry.execute(name, args)
            last_progress_at = time.monotonic()
            ok = bool(exec_out.get("ok"))
            if ok:
                consecutive_tool_failures = 0
            else:
                consecutive_tool_failures += 1
            will_retry = (not ok) and consecutive_tool_failures < max_tool_fail
            step_end_status = (
                "ok"
                if ok
                else ("tool_failed_will_retry" if will_retry else "failed")
            )
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_result",
                        json.dumps(
                            {
                                "step_id": round_sid,
                                "tool": name,
                                "ok": ok,
                                "result": exec_out.get("data"),
                                "error": exec_out.get("error"),
                                "fail_streak": consecutive_tool_failures,
                                "max_tool_fail_attempts": max_tool_fail,
                            },
                            ensure_ascii=False,
                        ),
                    )
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {
                                "step_id": round_sid,
                                "status": step_end_status,
                            },
                            ensure_ascii=False,
                        ),
                    )
            tool_trace.append(
                {
                    "round": round_idx,
                    "thought": thought_str,
                    "tool": name,
                    "args": args,
                    "ok": ok,
                    "data": exec_out.get("data"),
                    "error": exec_out.get("error"),
                    "fail_streak": consecutive_tool_failures,
                }
            )
            _append_observation(
                messages,
                {
                    "tool": name,
                    "ok": ok,
                    "result": exec_out.get("data"),
                    "error": exec_out.get("error"),
                },
            )
            if not ok:
                if will_retry:
                    messages.append(HumanMessage(content=TOOL_FAILURE_NUDGE))
                    continue
                err = str(exec_out.get("error") or "工具执行失败")
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        await event_repository.append_event(
                            db,
                            task_id,
                            "execution",
                            "error",
                            json.dumps(
                                {
                                    "message": err,
                                    "reason": "tool_failures_exhausted",
                                    "fail_streak": consecutive_tool_failures,
                                },
                                ensure_ascii=False,
                            ),
                        )
                return {
                    "outcome": "failed",
                    "error_message": err,
                    "summary": None,
                    "replan_requested": False,
                }
            continue

        # 既无终答也无有效 action：落库无效形状；达上限则失败，否则注入纠错提示后继续
        logger.warning(
            "react round %s: missing final_answer and action after alias normalize; keys=%s",
            round_idx,
            list(data.keys()),
        )
        excerpt = text.strip()
        if len(excerpt) > 1200:
            excerpt = excerpt[:1200] + "…"
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "execution",
                    "step_end",
                    json.dumps(
                        {
                            "step_id": round_sid,
                            "status": "invalid_react_shape",
                            "raw_excerpt": excerpt,
                        },
                        ensure_ascii=False,
                    ),
                )
        messages.append(HumanMessage(content=REACT_SHAPE_NUDGE))
        continue
