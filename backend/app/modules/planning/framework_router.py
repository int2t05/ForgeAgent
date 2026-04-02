"""规划域：任务入口认知框架路由。

在 plan_execute 与 react 之间选择认知模式，写入状态并记录 framework_selected 事件；
规则与常见 Plan-and-Execute / ReAct 分工一致。
"""

from __future__ import annotations

import json
import logging
from typing import Literal, cast

from langchain_core.messages import BaseMessage, SystemMessage

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.memory.session_context import SessionLLMContextManager
from app.modules.prompts.framework_router import FRAMEWORK_ROUTER_SYSTEM
from app.shared.llm_json_parse import parse_llm_json_object
from app.modules.workflow.state import AgentState
from app.repositories import event_repository

logger = logging.getLogger(__name__)

# 路由结果中的框架枚举（与 AgentState.cognitive_mode 取值一致）
CognitiveFramework = Literal["plan_execute", "react"]


def _default_framework() -> tuple[CognitiveFramework, str]:
    """在未配置 LLM 时返回默认认知框架与说明文案。"""
    return "react", "未配置 LLM，默认采用 ReAct。"


async def classify_cognitive_framework(
    chat_messages: list[BaseMessage],
) -> tuple[CognitiveFramework, str]:
    """根据会话消息选择 plan_execute 或 react，并产出供时间线展示的简短理由。"""
    settings = get_settings()
    # 1. 无可用模型时采用默认 ReAct
    if not is_llm_configured(settings):
        return _default_framework()
    chat = build_chat_model(settings)
    try:
        # 2. 调用路由模型并解析 JSON 选型结果
        msg = await ainvoke_with_retry(
            chat,
            [SystemMessage(content=FRAMEWORK_ROUTER_SYSTEM), *chat_messages],
            settings,
        )
        raw = getattr(msg, "content", None)
        text = raw if isinstance(raw, str) else str(raw or "")
        data = parse_llm_json_object(text)
        if not data:
            logger.warning("framework router output not valid JSON, using react")
            return "react", "路由输出无法解析为 JSON，回退为 ReAct。"
        # 3. 归一化 framework 与 reason 供下游与时间线使用
        fw = data.get("framework")
        reason = data.get("reason")
        if fw == "plan_execute":
            r = reason if isinstance(reason, str) and reason.strip() else "模型选用先规划后执行。"
            return "plan_execute", r.strip()
        r = reason if isinstance(reason, str) and reason.strip() else "模型选用 ReAct。"
        return "react", r.strip()
    except Exception:
        logger.exception("framework router LLM failed, using react")
        return "react", "路由 LLM 调用失败，回退为 ReAct。"


async def framework_router_node(state: AgentState) -> dict:
    """LangGraph 入口节点：解析认知模式写入状态，并落库 framework_selected 事件。"""
    task_id = state["task_id"]  # type: ignore
    session_id = state.get("session_id") or ""
    user_message = state.get("user_message") or ""
    settings = get_settings()
    # 1. 加载会话消息供路由决策（与 planner 消息窗口一致）
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        chat_messages = await mgr.load_chat_messages(
            db,
            session_id=session_id,
            fallback_user_content=user_message,
        )
    # 2. 执行认知框架分类
    fw, reason = await classify_cognitive_framework(chat_messages)
    payload = json.dumps(
        {"framework": fw, "reason": reason},
        ensure_ascii=False,
    )
    # 3. 持久化 framework_selected 供时间线展示
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await event_repository.append_event(
                db,
                task_id,
                "planning",
                "framework_selected",
                payload,
            )
    return {
        "cognitive_mode": cast(CognitiveFramework, fw),
        "framework_rationale": reason,
    }


def route_after_framework(state: AgentState) -> Literal["planner", "react"]:
    """按 cognitive_mode 返回 LangGraph 条件边目标（planner 或 react）。"""
    if state.get("cognitive_mode") == "react":
        return "react"
    return "planner"
