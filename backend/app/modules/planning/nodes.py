"""规划域 LangGraph 节点（Planner）：合并会话、黑板与规划模型输出，生成无工具绑定的抽象步骤并持久化。

若上轮请求重规划，则先递增计划版本并写相应事件。
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.memory.session_context import SessionLLMContextManager
from app.modules.planning.llm import plan_steps_with_llm
from app.modules.workflow.state import AgentState
from app.repositories import event_repository, task_repository

logger = logging.getLogger(__name__)

_FORCE_REPLAN_TOKEN = "__FORCE_REPLAN__"


def initial_force_replan_budget(user_message: str) -> int:
    """由用户消息推断初始预演/强制重规划预算（测试令牌触发时为 1，否则 0）。"""
    return 1 if _FORCE_REPLAN_TOKEN in user_message else 0


async def planner_node(state: AgentState) -> dict:
    """产出并写回 ``plan_steps``，同步规划链上事件与重规划计数器。"""
    task_id = state["task_id"]  # type: ignore
    user_message = state.get("user_message") or ""
    session_id = state.get("session_id") or ""
    settings = get_settings()
    out: dict = {}

    # 1. 若上一跳请求重规划：提升 ``plan_version``、写 ``replan`` 并累加计数
    if state.get("replan_requested"):
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
            "task %s replan in planner: plan_version=%s replan_count=%s",
            task_id,
            new_version,
            next_count,
        )
        out["replan_count"] = next_count
        out["replan_requested"] = False

    # 2. 组装会话消息与黑板条，调用规划 LLM 得抽象步骤列表
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        chat_messages = await mgr.load_chat_messages(
            db,
            session_id=session_id,
            fallback_user_content=user_message,
        )
    notes = state.get("blackboard_notes") or []
    if notes:
        tail = notes[-10:]
        bb = "【共享黑板·来自 Learner 的要点】\n" + "\n".join(tail)
        chat_messages = [*chat_messages, HumanMessage(content=bb)]
    steps = await plan_steps_with_llm(chat_messages, settings)

    payload = json.dumps({"steps": steps}, ensure_ascii=False)
    # 3. 落库 ``plan_created`` 并复位 ``current_step_index``
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "planning",
                "plan_created",
                payload,
            )
    out["plan_steps"] = steps
    out["current_step_index"] = 0
    return out
