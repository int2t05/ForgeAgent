"""执行域 LangGraph 节点（Actor）：按步 ReAct、可观测事件落库、全任务流式总结。"""

from __future__ import annotations

import json
import time
from typing import Literal

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.execution.llm_reply import assistant_reply_stream_with_llm
from app.modules.execution.step_executor import execute_plan_step_react
from app.modules.tools.registry import tool_registry
from app.modules.workflow.state import AgentState
from app.repositories import event_repository
from app.schemas.tools import ToolItem

_TK_O = "\u003cthink\u003e"
_TK_C = "\u003c/think\u003e"


class _StreamDeltaBatcher:
    """流式总结 LLM 输出的按相位缓冲与批量刷写。"""

    def __init__(self, task_id: str, step_id: str | None = None) -> None:
        self._task_id = task_id
        self._step_id = step_id
        self._pending: dict[str, list[str]] = {
            "thinking": [],
            "action": [],
            "answer": [],
        }
        self._buf_chars = 0
        self._last_flush = time.monotonic()

    async def add(self, phase: str, delta: str) -> None:
        """写入一帧流式文本；字符量或时间超过阈值时刷库。"""
        if not delta or phase not in self._pending:
            return
        self._pending[phase].append(delta)
        self._buf_chars += len(delta)
        now = time.monotonic()
        if self._buf_chars >= 480 or (now - self._last_flush) >= 0.12:
            await self.flush()

    async def flush(self) -> None:
        """将各相位剩余缓冲合并写入 ``llm_stream_delta`` 事件。"""
        for ph in ("thinking", "action", "answer"):
            if not self._pending[ph]:
                continue
            merged = "".join(self._pending[ph])
            self._pending[ph].clear()
            obj: dict[str, object] = {"phase": ph, "delta": merged}
            if self._step_id:
                obj["step_id"] = self._step_id
            payload = json.dumps(obj, ensure_ascii=False)
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        self._task_id,
                        "execution",
                        "llm_stream_delta",
                        payload,
                    )
        self._buf_chars = 0
        self._last_flush = time.monotonic()


def _executable_tools_for_selection() -> list[ToolItem]:
    """当前内置且已在注册表中可执行的 ``ToolItem`` 列表。"""
    return [t for t in tool_registry.list_tools_public().tools if t.source == "builtin"]


async def actor_node(state: AgentState) -> dict:
    """按计划逐步 ReAct 执行，并生成面向用户的 ``summary`` 与 ``actor_tool_trace``。"""
    task_id = state["task_id"]  # type: ignore
    plan_steps = state.get("plan_steps") or []
    tool_trace: list[dict] = []

    settings_exec = get_settings()
    max_tool_tries = max(1, int(settings_exec.max_tool_failure_attempts or 3))
    max_react_rounds = max(1, int(settings_exec.max_react_rounds_per_step or 20))
    user_message_exec = state.get("user_message") or ""
    exec_tools = _executable_tools_for_selection()

    for step in plan_steps:
        trace_row = await execute_plan_step_react(
            task_id,
            step,
            user_message=user_message_exec,
            prior_tool_trace=tool_trace,
            tools=exec_tools,
            settings=settings_exec,
            max_tool_tries=max_tool_tries,
            max_react_rounds=max_react_rounds,
        )
        tool_trace.append(trace_row)

    # 根据计划与工具轨迹调用总结模型并推送流式增量
    user_message = state.get("user_message") or ""
    settings = get_settings()
    full_t = ""
    full_a = ""
    batcher = _StreamDeltaBatcher(task_id)
    try:
        async for phase, delta in assistant_reply_stream_with_llm(
            user_message,
            plan_steps,
            settings,
            tool_trace=tool_trace,
        ):
            if phase == "thinking":
                full_t += delta
            else:
                full_a += delta
            await batcher.add(phase, delta)
    finally:
        await batcher.flush()

    if full_t.strip():
        summary = f"{_TK_O}{full_t.strip()}{_TK_C}\n\n{full_a.strip()}"
    else:
        summary = full_a.strip() or "任务已完成（LangGraph 最小闭环）"
    return {
        "outcome": "success",
        "summary": summary,
        "replan_requested": False,
        "actor_tool_trace": tool_trace,
    }


def route_after_learner(state: AgentState) -> Literal["planner", "done"]:
    """Learner 之后的条件边目标：``planner`` 或图结束。"""
    if state.get("outcome") == "failed":
        return "done"
    if state.get("replan_requested"):
        return "planner"
    return "done"


executor_node = actor_node
route_after_executor = route_after_learner
route_after_actor = route_after_learner
