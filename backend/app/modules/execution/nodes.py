"""Act 模块：每步循环执行 → 收集工具上下文。

核心职责：
1. 按计划步骤循环执行
2. 每步调用 ReAct 循环
3. 收集工具调用结果和上下文
4. 不生成最终回答（由 Learn 负责）
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import get_settings
from app.core.database import get_db_session
from app.modules.execution.step_executor import execute_plan_step_react
from app.modules.tools.registry import tool_registry
from app.modules.workflow.state import AgentState
from app.repositories import event_repository
from app.schemas.tools import ToolItem

logger = logging.getLogger(__name__)


class _StreamDeltaBatcher:
    """流式输出按相位缓冲与批量刷写。"""

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
        if not delta or phase not in self._pending:
            return
        self._pending[phase].append(delta)
        self._buf_chars += len(delta)
        now = time.monotonic()
        if self._buf_chars >= 1200 or (now - self._last_flush) >= 0.25:
            await self.flush()

    async def flush(self) -> None:
        payloads: list[str] = []
        for ph in ("thinking", "action", "answer"):
            if not self._pending[ph]:
                continue
            merged = "".join(self._pending[ph])
            self._pending[ph].clear()
            obj: dict[str, object] = {"phase": ph, "delta": merged}
            if self._step_id:
                obj["step_id"] = self._step_id
            payloads.append(json.dumps(obj, ensure_ascii=False))
        if payloads:
            async with get_db_session() as db:
                async with db.begin():
                    for payload in payloads:
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
    return [
        t for t in tool_registry.list_tools_public().tools
        if t.source in ("builtin", "mcp")
    ]


async def act_node(state: AgentState) -> dict:
    """Act 节点：每步循环执行，收集工具上下文。

    流程：
    1. 遍历计划步骤
    2. 每步执行 ReAct 循环
    3. 收集工具调用结果
    4. 返回上下文给 Learn
    """
    task_id = state["task_id"] # type: ignore
    plan_steps = state.get("plan_steps") or []
    tool_trace: list[dict] = []
    step_results: list[dict] = []

    settings = get_settings()
    max_tool_tries = max(1, int(settings.max_tool_failure_attempts or 3))
    max_react_rounds = max(1, int(settings.max_react_rounds_per_step or 20))
    user_message = state.get("user_message") or ""
    exec_tools = _executable_tools_for_selection()

    all_ok = True

    for idx, step in enumerate(plan_steps):
        step_id = step.get("id") or f"step-{idx + 1}"
        step_title = step.get("title") or f"步骤 {idx + 1}"

        trace_row = await execute_plan_step_react(
            task_id,
            step,
            user_message=user_message,
            prior_tool_trace=tool_trace,
            tools=exec_tools,
            settings=settings,
            max_tool_tries=max_tool_tries,
            max_react_rounds=max_react_rounds,
        )
        tool_trace.append(trace_row)

        step_ok = trace_row.get("ok", False)
        if not step_ok:
            all_ok = False

        step_results.append({
            "step_id": step_id,
            "title": step_title,
            "ok": step_ok,
            "step_final_answer": trace_row.get("step_final_answer"),
            "calls": trace_row.get("calls", []),
        })

        logger.info(
            "Act: step %s (%s) completed, ok=%s",
            step_id,
            step_title,
            step_ok,
        )

    act_context = {
        "plan_steps": plan_steps,
        "tool_trace": tool_trace,
        "step_results": step_results,
        "all_ok": all_ok,
    }

    return {
        "act_context": act_context,
        "act_tool_trace": tool_trace,
        "act_step_results": step_results,
        "outcome": "success" if all_ok else "failed",
        "replan_requested": False,
    }


actor_node = act_node
