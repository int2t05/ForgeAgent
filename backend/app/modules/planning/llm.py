"""规划域：基于 LLM 的任务步骤生成；步骤 JSON 解析见 ``app.shared.llm_json_parse``。

无可用密钥或解析失败时回退内置默认步骤；工具目录来自统一注册表。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.messages import BaseMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.prompts.planning import build_planner_system_prompt
from app.schemas.tools import ToolItem
from app.shared.llm_json_parse import parse_llm_json_object

logger = logging.getLogger(__name__)

_DEFAULT_STEPS: list[dict[str, Any]] = [
    {"id": "1", "title": "理解用户输入与上下文"},
    {"id": "2", "title": "按步执行并汇总结果"},
]


def _normalize_steps(
    data: dict[str, Any],
    *,
    allowed_tool_names: frozenset[str],
) -> list[dict[str, Any]] | None:
    """校验步骤列表；可选 ``tool``、``args``；``tool`` 须在 ``allowed_tool_names`` 内。"""
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) < 1:
        return None
    out: list[dict[str, Any]] = []
    for i, item in enumerate(steps):
        if not isinstance(item, dict):
            return None
        sid = str(item.get("id") or str(i + 1))
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        row: dict[str, Any] = {"id": sid, "title": title.strip()}
        raw_tool = item.get("tool")
        if isinstance(raw_tool, str) and raw_tool.strip():
            tname = raw_tool.strip()
            if tname not in allowed_tool_names:
                logger.warning("planner step references unknown tool %r", tname)
                return None
            row["tool"] = tname
            args: dict[str, Any] = {}
            raw_args = item.get("args")
            if isinstance(raw_args, dict):
                args = cast(dict[str, Any], raw_args)
            elif isinstance(raw_args, str) and raw_args.strip():
                try:
                    parsed = json.loads(raw_args.strip())
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    args = cast(dict[str, Any], parsed)
            row["args"] = args
        out.append(row)
    return out


async def plan_steps_with_llm(
    chat_messages: Sequence[BaseMessage],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """依据会话消息生成计划步骤列表；解析失败或非法时回退默认步骤。"""
    # 1. 延迟导入工具注册表，避免配置加载阶段循环依赖
    from app.modules.tools.registry import tool_registry

    s = settings or get_settings()
    # 2. 无 API 配置时返回内置默认计划
    if not is_llm_configured(s):
        return list(_DEFAULT_STEPS)

    tools = tool_registry.list_tools_public().tools
    allowed_tool_names = frozenset(t.name for t in tools)
    chat = build_chat_model(s)
    sys = build_planner_system_prompt(tools)
    # 3. 调用规划模型，解析 JSON 并校验步骤与工具名
    try:
        msg = await ainvoke_with_retry(
            chat, [SystemMessage(content=sys), *list(chat_messages)], s
        )
        content = getattr(msg, "content", None)
        text = content if isinstance(content, str) else str(content or "")
        data = parse_llm_json_object(text)
        if data is None:
            logger.warning("planner LLM output not valid JSON, using default steps")
            return list(_DEFAULT_STEPS)
        normalized = _normalize_steps(data, allowed_tool_names=allowed_tool_names)
        if not normalized:
            logger.warning("planner LLM steps invalid, using default steps")
            return list(_DEFAULT_STEPS)
        return normalized
    except Exception:
        logger.exception("planner LLM call failed, using default steps")
        return list(_DEFAULT_STEPS)
