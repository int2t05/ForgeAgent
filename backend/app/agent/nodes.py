"""LangGraph 节点：规划、执行、重规划落库（异步 + 独立会话）。"""

from __future__ import annotations

import json
import logging
from typing import Literal

from app.database import AsyncSessionLocal
from app.repositories import event_repository, task_repository
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_FORCE_REPLAN_TOKEN = "__FORCE_REPLAN__"


def initial_force_replan_budget(user_message: str) -> int:
    """若含测试令牌则计 1 次可消费重规划请求（避免每轮计划后重复匹配同一段用户文本）。"""
    return 1 if _FORCE_REPLAN_TOKEN in user_message else 0


async def planner_node(state: AgentState) -> dict:
    """规划节点：生成可展示步骤并写入 plan_created。"""
    # 1. 组装固定两步计划（MVP 无 LLM 时的确定性行为，便于测试）
    task_id = state["task_id"]  # type: ignore

    steps = [
        {"id": "1", "title": "理解用户输入与上下文"},
        {"id": "2", "title": "按步执行并汇总结果"},
    ]

    payload = json.dumps({"steps": steps}, ensure_ascii=False)
    # 2. 追加 task_events(kind=plan_created)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "planning",
                "plan_created",
                payload,
            )
    return {"plan_steps": steps, "current_step_index": 0}


async def executor_node(state: AgentState) -> dict:
    """执行节点：逐步写入 step_start；按需标记重规划或终态。"""
    # 1. 按 plan_steps 顺序追加 step_start 事件
    task_id = state["task_id"]  # type: ignore
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
        # 2. force_replan_budget>0 且 replan_count<max → 消耗预算并请求 replan_record
        if replan_count < max_r:
            return {
                "replan_requested": True,
                "force_replan_budget": budget - 1,
            }
        # 3. budget>0 但已达上限 → outcome=failed 并写 error 事件
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
    # 4. 否则 outcome=success
    return {
        "outcome": "success",
        "summary": "任务已完成（LangGraph 最小闭环）",
        "replan_requested": False,
    }  # 节点返回的 dict 会与当前状态浅合并


async def replan_record_node(state: AgentState) -> dict:
    """重规划节点：plan_version 自增并写入 kind=replan。"""
    # 1. tasks.plan_version += 1
    task_id = state["task_id"]  # type: ignore
    new_version = 0
    # 2. task_events 追加 replan（payload 带新版本号）
    async with AsyncSessionLocal() as db:
        async with db.begin():
            new_version = await task_repository.bump_plan_version(db, task_id)
            await event_repository.append_event(
                db,
                task_id,
                "planning",
                "replan",
                json.dumps({"plan_version": new_version}, ensure_ascii=False),
            )
    # 3. 递增 state.replan_count 并清除 replan_requested
    next_count = int(state.get("replan_count") or 0) + 1
    logger.info(
        "task %s replan recorded: plan_version=%s replan_count=%s",
        task_id,
        new_version,
        next_count,
    )
    return {
        "replan_count": next_count,
        "replan_requested": False,
    }


def route_after_executor(state: AgentState) -> Literal["replan", "done"]:
    """执行后路由：已成功/失败直出；仅未终态且显式请求时进入重规划。"""
    if state.get("outcome") in ("success", "failed"):
        return "done"
    if state.get("replan_requested"):
        return "replan"
    return "done"
