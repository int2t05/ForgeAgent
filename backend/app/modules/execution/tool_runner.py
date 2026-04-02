"""单工具执行：落库 ``tool_call`` / ``tool_result``，失败时按次数重试。

由 ReAct 步内循环与同类执行路径共用。
"""

from __future__ import annotations

import json
from typing import Any

from app.core.database import AsyncSessionLocal
from app.modules.tools.registry import tool_registry
from app.repositories import event_repository


async def run_single_tool_with_retry(
    task_id: str,
    step_id: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    max_tool_tries: int,
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    """执行单次命名工具调用并返回是否最终成功、末次结果与各次尝试记录。"""
    # 1. 记录即将执行的调用（含步与重试上限元数据）
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "tool",
                "tool_call",
                json.dumps(
                    {
                        "step_id": step_id,
                        "tool": tool_name,
                        "args": tool_args,
                        "max_attempts": max_tool_tries,
                    },
                    ensure_ascii=False,
                ),
            )

    # 2. 在次数上限内执行注册表并逐次落库结果，成功即提前结束
    attempt_rows: list[dict[str, Any]] = []
    final_ok = False
    last_exec: dict[str, Any] = {"ok": False, "data": None, "error": None}
    for attempt in range(1, max_tool_tries + 1):
        exec_out = await tool_registry.execute(tool_name, tool_args)
        last_exec = {
            "ok": bool(exec_out.get("ok")),
            "data": exec_out.get("data"),
            "error": exec_out.get("error"),
        }
        ok = last_exec["ok"]
        attempt_rows.append(
            {
                "attempt": attempt,
                "ok": ok,
                "data": exec_out.get("data"),
                "error": exec_out.get("error"),
            }
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
                            "step_id": step_id,
                            "tool": tool_name,
                            "attempt": attempt,
                            "max_attempts": max_tool_tries,
                            "ok": ok,
                            "result": exec_out.get("data"),
                            "error": exec_out.get("error"),
                        },
                        ensure_ascii=False,
                    ),
                )
        if ok:
            final_ok = True
            break

    return final_ok, last_exec, attempt_rows
