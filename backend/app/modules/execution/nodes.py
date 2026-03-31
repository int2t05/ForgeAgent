"""LangGraph 执行侧节点：步骤事件、流式应答、终态与重规划请求。"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.execution.llm_reply import assistant_reply_stream_with_llm
from app.modules.tools.registry import tool_registry
from app.modules.workflow.state import AgentState
from app.repositories import event_repository

logger = logging.getLogger(__name__)

_TK_O = "\u003cthink\u003e"
_TK_C = "\u003c/think\u003e"


class _StreamDeltaBatcher:
    """llm_stream_delta 批量落库（减 SQLite 写入次数）。"""

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
        """将流式片段暂存，并在达到字符或时间阈值时触发刷盘。"""
        if not delta or phase not in self._pending:
            return
        self._pending[phase].append(delta)
        self._buf_chars += len(delta)
        now = time.monotonic()
        if self._buf_chars >= 480 or (now - self._last_flush) >= 0.12:
            await self.flush()

    async def flush(self) -> None:
        """将 thinking / action / answer 缓冲合并为 llm_stream_delta 事件写入库。"""
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


def _step_tool_and_args(step: dict) -> tuple[str | None, dict]:
    """从计划步骤中解析工具名与参数（非字符串 tool 视为无工具）。"""
    raw = step.get("tool")
    if not isinstance(raw, str) or not raw.strip():
        return None, {}
    args = step.get("args")
    if isinstance(args, dict):
        return raw.strip(), dict(args)
    return raw.strip(), {}


async def executor_node(state: AgentState) -> dict:
    """LangGraph 执行节点：按计划（或强制重规划预演）落库执行事件，并流式生成汇总答复。"""
    # 1. 解析任务、计划步骤、重规划与强制预演预算
    task_id = state["task_id"]  # type: ignore
    plan_steps = state.get("plan_steps") or []
    max_r = int(state.get("max_replan_attempts") or 0)
    replan_count = int(state.get("replan_count") or 0)
    budget = int(state.get("force_replan_budget") or 0)
    tool_trace: list[dict] = []
    # 2. 强制重规划预算大于零时：仅为各步骤写入 step_start，不调用工具
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
        # 3. 正常执行：逐步写入步骤与工具事件并累计 tool_trace
        for step in plan_steps:
            sid = step.get("id")
            title = step.get("title")
            tool_name, tool_args = _step_tool_and_args(step)

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
            # 未声明工具则标记跳过并进入下一步
            if not tool_name:
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
                                    "status": "skipped_no_tool",
                                },
                                ensure_ascii=False,
                            ),
                        )
                tool_trace.append(
                    {
                        "step_id": sid,
                        "title": title,
                        "tool": None,
                        "skipped_no_tool": True,
                    }
                )
                continue

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_call",
                        json.dumps(
                            {
                                "step_id": sid,
                                "tool": tool_name,
                                "args": tool_args,
                            },
                            ensure_ascii=False,
                        ),
                    )
            # 经注册表执行工具并依据结果决定是否提前失败退出
            exec_out = await tool_registry.execute(tool_name, tool_args)
            ok = bool(exec_out.get("ok"))

            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await event_repository.append_event(
                        db,
                        task_id,
                        "tool",
                        "tool_result",
                        json.dumps(
                            {
                                "step_id": sid,
                                "tool": tool_name,
                                "ok": ok,
                                "result": exec_out.get("data"),
                                "error": exec_out.get("error"),
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
                                "step_id": sid,
                                "status": "failed" if not ok else "ok",
                            },
                            ensure_ascii=False,
                        ),
                    )

            tool_trace.append(
                {
                    "step_id": sid,
                    "title": title,
                    "tool": tool_name,
                    "args": tool_args,
                    "ok": ok,
                    "data": exec_out.get("data"),
                    "error": exec_out.get("error"),
                }
            )

            if not ok:
                err = str(exec_out.get("error") or "工具执行失败")
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

    # 4. 仅预演 step_start：返回重规划请求或超次失败，不进入总结 LLM
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

    # 5. 流式调用 LLM 生成最终 thinking/answer 并批量写入流式增量事件
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
    }


def route_after_executor(state: AgentState) -> Literal["replan", "done"]:
    """依据图状态选择执行结束后是结束还是进入重规划分支。"""
    if state.get("outcome") in ("success", "failed"):
        return "done"
    if state.get("replan_requested"):
        return "replan"
    return "done"
