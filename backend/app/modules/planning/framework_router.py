"""规划域：任务入口认知框架路由。

根据会话上下文在 plan_execute 与 react 之间选型，并落库 framework_selected 事件；
选型规则与 LangGraph 常见的 Plan-and-Execute / ReAct 分工对齐。
"""

from __future__ import annotations

import json
import logging
from typing import Literal, cast

from langchain_core.messages import BaseMessage, SystemMessage

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.modules.memory.session_context import SessionLLMContextManager
from app.modules.planning.llm import parse_llm_json_object
from app.modules.workflow.state import AgentState
from app.repositories import event_repository

logger = logging.getLogger(__name__)

# 路由结果中的框架枚举（与 AgentState.cognitive_mode 取值一致）
CognitiveFramework = Literal["plan_execute", "react"]

_FRAMEWORK_ROUTER_SYSTEM = """你是认知框架路由助手。根据用户当前任务与会话上下文，只输出一个 JSON 对象，不要 markdown 代码块、不要额外说明。

【两种框架】（与业界 Plan-and-Execute 与 ReAct 的常见划分一致）：
- "plan_execute"：目标可预先拆解为多步；适合「先规划再逐步执行」；步骤相对独立或批次明确。
- "react"：强依赖「推理 → 行动 → 观察」紧耦合循环；下一步高度取决于工具/环境反馈；探索性、单焦点问答或查数类。

【输出形状】
{"framework":"plan_execute" 或 "react","reason":"一句中文简述选型理由"}

【原则】
- 用户明确要求「列计划」「分步骤」「先规划」→ plan_execute。
- 单轮事实查询、需多次试工具/看观测再决定 → react。
- 不确定时选 plan_execute。"""


def _default_framework() -> tuple[CognitiveFramework, str]:
    """在未配置 LLM 时返回保守默认框架与说明文案。"""
    return "plan_execute", "未配置 LLM，默认采用先规划后执行。"


async def classify_cognitive_framework(
    chat_messages: list[BaseMessage],
) -> tuple[CognitiveFramework, str]:
    """根据会话消息列表返回应采用的认知框架及简要理由。"""
    settings = get_settings()
    # 1. 无可用模型时直接走历史默认路径
    if not is_llm_configured(settings):
        return _default_framework()
    chat = build_chat_model(settings)
    try:
        # 2. 调用路由模型并解析 JSON
        msg = await chat.ainvoke(
            [SystemMessage(content=_FRAMEWORK_ROUTER_SYSTEM), *chat_messages]
        )
        raw = getattr(msg, "content", None)
        text = raw if isinstance(raw, str) else str(raw or "")
        data = parse_llm_json_object(text)
        if not data:
            logger.warning("framework router output not valid JSON, using plan_execute")
            return "plan_execute", "路由输出无法解析为 JSON，回退为先规划后执行。"
        # 3. 归一化 framework 与 reason 字段
        fw = data.get("framework")
        reason = data.get("reason")
        if fw == "react":
            r = reason if isinstance(reason, str) and reason.strip() else "模型选用 ReAct。"
            return "react", r.strip()
        r = reason if isinstance(reason, str) and reason.strip() else "模型选用先规划后执行。"
        return "plan_execute", r.strip()
    except Exception:
        logger.exception("framework router LLM failed, using plan_execute")
        return "plan_execute", "路由 LLM 调用失败，回退为先规划后执行。"


async def framework_router_node(state: AgentState) -> dict:
    """LangGraph 节点：写入框架选型状态并追加 planning/framework_selected 事件。"""
    task_id = state["task_id"]  # type: ignore
    session_id = state.get("session_id") or ""
    user_message = state.get("user_message") or ""
    settings = get_settings()
    # 1. 加载会话最近消息窗口（与 planner 一致）
    mgr = SessionLLMContextManager(settings.session_memory_max_messages)
    async with AsyncSessionLocal() as db:
        chat_messages = await mgr.load_chat_messages(
            db,
            session_id=session_id,
            fallback_user_content=user_message,
        )
    # 2. 调用选型逻辑得到框架与理由
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
    """条件边：由 cognitive_mode 决定下一节点别名（planner 或 react）。"""
    if state.get("cognitive_mode") == "react":
        return "react"
    return "planner"
