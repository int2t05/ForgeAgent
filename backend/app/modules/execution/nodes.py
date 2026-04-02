"""执行域 LangGraph 节点（Actor）：按步 ReAct、可观测事件落库、全任务流式总结。

预演预算下仅打步骤骨架事件，真正执行在预算耗尽后的路径完成。
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.execution.llm_reply import assistant_reply_stream_with_llm
from app.modules.execution.step_react_loop import run_step_react_loop
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
    """驱动逐步执行或预演短路径，并生成面向用户的 ``summary`` 与 ``actor_tool_trace``。"""
    # 1. 读取任务 id、计划步、重规划上限与预演预算
    task_id = state["task_id"]  # type: ignore
    plan_steps = state.get("plan_steps") or []
    max_r = int(state.get("max_replan_attempts") or 0)
    replan_count = int(state.get("replan_count") or 0)
    budget = int(state.get("force_replan_budget") or 0)
    tool_trace: list[dict] = []
    # 2. 预演预算大于零时仅连续发送各步 ``step_start``
    if budget > 0:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                for step in plan_steps:
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_start",
                        json.dumps(
                            {
                                "step_id": step.get("id"),
                                "title": step.get("title"),
                            },
                            ensure_ascii=False,
                        ),
                    )
    else:
        # 3. 正常执行：逐步 ``step_start``、ReAct、``step_end`` 与轨迹聚合
        settings_exec = get_settings()
        max_tool_tries = max(1, int(settings_exec.max_tool_failure_attempts or 3))
        max_react_rounds = max(1, int(settings_exec.max_react_rounds_per_step or 8))
        user_message_exec = state.get("user_message") or ""
        exec_tools = _executable_tools_for_selection()

        for step in plan_steps:
            sid = step.get("id")
            title = step.get("title")

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_start",
                        json.dumps(
                            {"step_id": sid, "title": title},
                            ensure_ascii=False,
                        ),
                    )

            ok_loop, call_results, step_ans = await run_step_react_loop(
                task_id,
                sid,
                step,
                user_message=user_message_exec,
                prior_tool_trace=tool_trace,
                tools=exec_tools,
                settings=settings_exec,
                max_tool_tries=max_tool_tries,
                max_rounds=max_react_rounds,
            )

            total_attempts = sum(
                len(c.get("attempts") or [])
                for c in call_results
                if isinstance(c, dict)
            )
            last_err: str | None = None
            for c in reversed(call_results):
                if isinstance(c, dict) and not c.get("ok"):
                    e = c.get("error")
                    last_err = e if isinstance(e, str) else None
                    break

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "execution",
                        "step_end",
                        json.dumps(
                            {
                                "step_id": sid,
                                "status": "ok" if ok_loop else "failed",
                                "attempts": total_attempts,
                            },
                            ensure_ascii=False,
                        ),
                    )

            tool_trace.append(
                {
                    "step_id": sid,
                    "title": title,
                    "react_loop": True,
                    "calls": call_results,
                    "step_final_answer": step_ans,
                    "ok": ok_loop,
                    "error": last_err,
                }
            )

    # 4. 预演分支：在次数允许时请求再规划，否则失败终态
    if budget > 0:
        if replan_count < max_r:
            return {
                "replan_requested": True,
                "force_replan_budget": budget - 1,
                "actor_tool_trace": [],
            }
        err = "超过最大重规划次数"
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await event_repository.append_event(
                    db,
                    task_id,
                    "execution",
                    "error",
                    json.dumps({"message": err}, ensure_ascii=False),
                )
        return {
            "outcome": "failed",
            "error_message": err,
            "summary": None,
            "replan_requested": False,
            "actor_tool_trace": [],
        }

    # 5. 根据计划与工具轨迹调用总结模型并推送流式增量
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
