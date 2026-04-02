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

async def planner_node(state: AgentState) -> dict:
    """产出并写回 ``plan_steps``，同步规划链上事件与重规划计数器。"""
    task_id = state["task_id"]  # type: ignore
    user_message = state.get("user_message") or ""
    session_id = state.get("session_id") or ""
    settings = get_settings()
    out: dict = {}

    # 1. 重规划写库与加载会话消息同连接（中间不夹 LLM，避免多开一次连接）
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        if state.get("replan_requested"):
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
    # 2. 组装黑板条后调用规划 LLM（释放上一条 DB 会话后再跑模型，避免长时间占连接）
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
