"""LangGraph 执行侧节点：步骤事件、流式应答、终态与重规划请求。"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.execution.llm_reply import assistant_reply_stream_with_llm
from app.modules.workflow.state import AgentState
from app.repositories import event_repository

logger = logging.getLogger(__name__)

_TK_O = "\u003cthink\u003e"
_TK_C = "\u003c/think\u003e"


class _StreamDeltaBatcher:
    """llm_stream_delta 批量落库（减 SQLite 写入次数）。"""

    def __init__(self, task_id: str) -> None:
        self._task_id = task_id
        self._pending: dict[str, list[str]] = {"thinking": [], "answer": []}
        self._buf_chars = 0
        self._last_flush = time.monotonic()

    async def add(self, phase: str, delta: str) -> None:
        if not delta:
            return
        self._pending[phase].append(delta)
        self._buf_chars += len(delta)
        now = time.monotonic()
        if self._buf_chars >= 480 or (now - self._last_flush) >= 0.12:
            await self.flush()

    async def flush(self) -> None:
        for ph in ("thinking", "answer"):
            if not self._pending[ph]:
                continue
            merged = "".join(self._pending[ph])
            self._pending[ph].clear()
            payload = json.dumps({"phase": ph, "delta": merged}, ensure_ascii=False)
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


async def executor_node(state: AgentState) -> dict:
    """执行节点：逐步写入 step_start；按需标记重规划或终态。"""
    task_id = state["task_id"]
    plan_steps = state.get("plan_steps") or []
    max_r = int(state.get("max_replan_attempts") or 0)
    replan_count = int(state.get("replan_count") or 0)
    budget = int(state.get("force_replan_budget") or 0)

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

    if budget > 0:
        if replan_count < max_r:
            return {
                "replan_requested": True,
                "force_replan_budget": budget - 1,
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
        }

    user_message = state.get("user_message") or ""
    settings = get_settings()
    full_t = ""
    full_a = ""
    batcher = _StreamDeltaBatcher(task_id)
    try:
        async for phase, delta in assistant_reply_stream_with_llm(
            user_message, plan_steps, settings
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
    }


def route_after_executor(state: AgentState) -> Literal["replan", "done"]:
    """执行后路由：已成功/失败直出；仅未终态且显式请求时进入重规划。"""
    if state.get("outcome") in ("success", "failed"):
        return "done"
    if state.get("replan_requested"):
        return "replan"
    return "done"
