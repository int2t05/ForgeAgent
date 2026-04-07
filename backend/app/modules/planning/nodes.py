"""Plan 模块：获取会话上下文 → 生成步骤。

核心职责：
1. 加载会话历史消息
2. 读取黑板要点
3. 检索 RAG 知识库
4. 选择相关技能
5. 调用 LLM 生成计划步骤
6. 持久化 plan_created 事件
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage

from app.core.config import get_settings
from app.core.database import get_db_session
from app.modules.memory.context import SessionLLMContextManager
from app.modules.memory.rag_integration import build_rag_context_for_planner
from app.modules.planning.llm import plan_steps_with_llm, select_skills_for_planner
from app.modules.tools.skill_sources import skill_import_context_from_paths
from app.modules.workflow.state import AgentState
from app.repositories import event_repository, task_repository
from app.services.settings_service import get_settings_public

logger = logging.getLogger(__name__)


async def plan_node(state: AgentState) -> dict:
    """Plan 节点：获取会话上下文，生成计划步骤。

    流程：
    1. 如果是重规划，递增计划版本
    2. 加载会话历史消息
    3. 检索 RAG 知识库（自动获取相关文档）
    4. 选择相关技能并注入上下文
    5. 读取黑板要点
    6. 调用 LLM 生成步骤
    7. 持久化事件
    """
    task_id = state["task_id"] # type: ignore
    user_message = state.get("user_message") or ""
    session_id = state.get("session_id") or ""
    settings = get_settings()
    out: dict = {}

    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with get_db_session() as db:
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
                "Plan: replan task=%s plan_version=%s replan_count=%s",
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
            settings=settings,
        )
        configured_skills = (await get_settings_public(db)).skills_paths

    # 3. 检索 RAG 知识库，将相关文档注入上下文
    rag_messages = await build_rag_context_for_planner(
        user_message,
        settings=settings,
    )

    selected_skill_paths: list[str] = []
    if configured_skills:
        selected_skill_paths = await select_skills_for_planner(
            chat_messages,
            settings,
            configured_skill_paths=configured_skills,
        )
        if selected_skill_paths:
            ctx = skill_import_context_from_paths(selected_skill_paths).strip()
            if ctx:
                chat_messages = [
                    *chat_messages,
                    HumanMessage(
                        content="【Skill 上下文】\n\n" + ctx
                    ),
                ]

    # 注入 RAG 检索结果
    chat_messages.extend(rag_messages)

    notes = state.get("blackboard_notes") or []
    if notes:
        tail = notes[-10:]
        bb = "【黑板要点·来自 Learn】\n" + "\n".join(tail)
        chat_messages = [*chat_messages, HumanMessage(content=bb)]

    steps = await plan_steps_with_llm(
        chat_messages,
        settings,
        configured_skill_paths=configured_skills,
    )

    payload = json.dumps({"steps": steps}, ensure_ascii=False)
    async with get_db_session() as db:
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
    out["act_context"] = {}
    out["act_tool_trace"] = []
    out["act_step_results"] = []

    logger.info("Plan: generated %d steps for task=%s", len(steps), task_id)
    return out


planner_node = plan_node
