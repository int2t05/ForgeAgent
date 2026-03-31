"""LangGraph 规划侧节点：生成计划、记录重规划。"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.memory.session_context import SessionLLMContextManager
from app.modules.planning.llm import plan_steps_with_llm
from app.modules.workflow.state import AgentState
from app.repositories import event_repository, task_repository

logger = logging.getLogger(__name__)

_FORCE_REPLAN_TOKEN = "__FORCE_REPLAN__"


def initial_force_replan_budget(user_message: str) -> int:
    """若含测试令牌则计 1 次可消费重规划请求（避免每轮计划后重复匹配同一段用户文本）。"""
    return 1 if _FORCE_REPLAN_TOKEN in user_message else 0


async def planner_node(state: AgentState) -> dict:
    """生成计划步骤并持久化 plan_created 事件。"""
    task_id = state["task_id"]  # type: ignore
    user_message = state.get("user_message") or ""
    session_id = state.get("session_id") or ""
    settings = get_settings()
    # 1. 将会话最近消息注入为 LangChain ChatMessages 后调用 LLM（或默认计划）
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        chat_messages = await mgr.load_chat_messages(
            db,
            session_id=session_id,
            fallback_user_content=user_message,
        )
    steps = await plan_steps_with_llm(chat_messages, settings)

    payload = json.dumps({"steps": steps}, ensure_ascii=False)
    # 2. 写入 planning 模块的 plan_created 事件
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
    """递增任务 plan_version 并写入 replan 事件，同时推进本地重规划计数。"""
    task_id = state["task_id"]  # type: ignore
    new_version = 0
    # 1. 同一事务内 bump 版本号并追加 planning/replan 事件
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
    # 2. 推进重规划计数并清除 replan 请求标志（供下一轮 planner 使用）
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
