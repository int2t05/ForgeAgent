"""LangGraph 规划侧节点：生成计划、记录重规划。"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.planning.llm import plan_steps_with_llm
from app.modules.workflow.state import AgentState
from app.repositories import event_repository, task_repository

logger = logging.getLogger(__name__)

_FORCE_REPLAN_TOKEN = "__FORCE_REPLAN__"


def initial_force_replan_budget(user_message: str) -> int:
    """若含测试令牌则计 1 次可消费重规划请求（避免每轮计划后重复匹配同一段用户文本）。"""
    return 1 if _FORCE_REPLAN_TOKEN in user_message else 0


async def planner_node(state: AgentState) -> dict:
    """规划节点：生成可展示步骤并写入 plan_created。"""
    task_id = state["task_id"]
    user_message = state.get("user_message") or ""
    settings = get_settings()
    steps = await plan_steps_with_llm(user_message, settings)

    payload = json.dumps({"steps": steps}, ensure_ascii=False)
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


async def replan_record_node(state: AgentState) -> dict:
    """重规划节点：plan_version 自增并写入 kind=replan。"""
    task_id = state["task_id"]
    new_version = 0
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
