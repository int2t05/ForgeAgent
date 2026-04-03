"""单计划步执行：与 Planner 解耦的 ReAct 落库单元（step_start → 循环 → step_end）。

由 Actor 节点按序调用，便于单独测试与替换执行策略。
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.core.database import get_db_session
from app.modules.execution.step_react_loop import run_step_react_loop
from app.modules.tools.skill_sources import skill_import_context_from_paths
from app.repositories import event_repository
from app.schemas.tools import ToolItem
from app.shared.workspace_snapshot import build_workspace_snapshot


def _step_skill_paths(step: dict[str, Any]) -> list[str]:
    raw = step.get("skill_imports")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str) and str(x).strip()]


async def execute_plan_step_react(
    task_id: str,
    step: dict[str, Any],
    *,
    user_message: str,
    prior_tool_trace: list[dict[str, Any]],
    tools: list[ToolItem],
    settings: Settings,
    max_tool_tries: int,
    max_react_rounds: int,
) -> dict[str, Any]:
    """单步落库起止事件并跑完 ReAct，返回与 ``actor_tool_trace`` 元素同形的汇总字典。"""
    sid = step.get("id")
    title = step.get("title")
    skill_ctx = skill_import_context_from_paths(_step_skill_paths(step))

    # 落库 step_start（短事务；ReAct 耗时不一定持有同一会话，以免占满连接池）
    async with get_db_session() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "execution",
                "step_start",
                json.dumps(
                    {"step_id": sid, "title": title} | build_workspace_snapshot(settings),
                    ensure_ascii=False,
                ),
            )

    # 执行 ReAct 循环（工具轮与终答）
    ok_loop, call_results, step_ans = await run_step_react_loop(
        task_id,
        sid,
        step,
        user_message=user_message,
        prior_tool_trace=prior_tool_trace,
        tools=tools,
        settings=settings,
        max_tool_tries=max_tool_tries,
        max_rounds=max_react_rounds,
        skill_import_text=skill_ctx,
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

    # 写入 step_end
    has_real_final = bool(step_ans)
    has_approval_rejected = any(
        isinstance(c, dict) and c.get("approval_rejected")
        for c in call_results
    )
    if has_approval_rejected:
        end_status = "cancelled"
    elif has_real_final:
        end_status = "ok"
    elif call_results:
        end_status = "no_final_answer"
    else:
        end_status = "failed"

    async with get_db_session() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "execution",
                "step_end",
                json.dumps(
                    {
                        "step_id": sid,
                        "status": end_status,
                        "attempts": total_attempts,
                    },
                    ensure_ascii=False,
                ),
            )

    # 返回本步轨迹条目
    return {
        "step_id": sid,
        "title": title,
        "react_loop": True,
        "calls": call_results,
        "step_final_answer": step_ans,
        "ok": ok_loop,
        "error": last_err,
    }
