"""基于 LLM 的计划步骤生成与 JSON 解析（无密钥时回退默认步骤）。"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.messages import BaseMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.schemas.tools import ToolItem

logger = logging.getLogger(__name__)

_DEFAULT_STEPS: list[dict[str, Any]] = [
    {"id": "1", "title": "理解用户输入与上下文"},
    {"id": "2", "title": "按步执行并汇总结果"},
]


def _tools_catalog_for_prompt(tools: Sequence[ToolItem]) -> str:
    """将注册表工具转为 LLM 可读目录（与 GET /tools 一致，便于扩展新工具无需改提示词模板）。"""
    catalog: list[dict[str, Any]] = []
    for t in tools:
        entry: dict[str, Any] = {
            "name": t.name,
            "description": t.description,
            "source": t.source,
        }
        if t.read_only is not None:
            entry["read_only"] = t.read_only
        if t.parameters:
            entry["parameters"] = t.parameters
        catalog.append(entry)
    return json.dumps(catalog, ensure_ascii=False, indent=2)


def build_planner_system_prompt(tools: Sequence[ToolItem]) -> str:
    """
    构造规划用 System 提示：固定输出契约 + 动态工具目录（LangChain/工具绑定常见做法：模型所见与注册表同步）。
    """
    catalog_block = _tools_catalog_for_prompt(tools)
    if tools:
        names_line = "、".join(t.name for t in tools)
        tool_rules = (
            "若某步需要调用工具：字段 \"tool\" 必须是【已注册工具】中某一个 \"name\"（精确匹配，区分大小写）；"
            "\"args\" 为 JSON 对象，键与取值须符合该工具的 \"parameters\"（JSON Schema），勿臆造字段名。"
        )
    else:
        names_line = "（当前无已注册工具）"
        tool_rules = "当前无可用工具：所有步骤均不得包含 \"tool\" 与 \"args\"。"

    return (
        "你是任务规划助手。根据用户与助手的前文对话及当前诉求，只输出一个 JSON 对象，"
        "不要 markdown 代码块、不要代码围栏、不要额外说明文字。\n\n"
        "【输出 JSON 形状】\n"
        '{"steps":[{"id":"步骤编号字符串","title":"步骤简述（简短中文）",'
        '"tool":"可选；仅当本步要调用工具时填写","args":{}}]}\n'
        "说明：分析与纯推理步骤可省略 \"tool\" 与 \"args\"；需要工具时必须同时给出二者。\n\n"
        "【步骤与工具约束】\n"
        f"- 至少 1 个步骤。\n"
        f"- {tool_rules}\n"
        f"- 当前允许的 tool 名称：{names_line}\n\n"
        "【已注册工具】（name、description、parameters 为入参 JSON Schema，可能为空）\n"
        f"{catalog_block}"
    )


def _strip_markdown_json_fence(text: str) -> str:
    """去掉 Markdown 中的 JSON 围栏。"""
    t = text.strip()
    if not t.startswith("```"):
        return t
    t = re.sub(r"^```(?:json)?\s*", "", t, count=1, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中尽量解析出 JSON 对象。"""
    raw = _strip_markdown_json_fence(text)
    s = raw.strip()
    dec = json.JSONDecoder()
    try:
        data = dec.raw_decode(s)[0]
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = dec.raw_decode(s, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


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
    """根据多轮会话消息产出计划步骤列表；未配置 LLM 或解析失败时使用默认两步。

    ``chat_messages`` 须为 LangChain ``BaseMessage`` 序列（通常为 user/assistant 交替）；
    规划 System 提示中的工具目录来自进程内 ``ToolRegistry`` 快照，与 GET /tools 一致，
    新增内置或 MCP/Skill 工具后无需再改此处硬编码列表。
    """
    # 延迟导入，避免在仅加载配置或未拉起注册表时形成不必要依赖
    from app.modules.tools.registry import tool_registry

    s = settings or get_settings()
    # 1. 无 API 配置时直接使用内置默认计划
    if not is_llm_configured(s):
        return list(_DEFAULT_STEPS)

    tools = tool_registry.list_tools_public().tools
    allowed_tool_names = frozenset(t.name for t in tools)
    chat = build_chat_model(s)
    sys = build_planner_system_prompt(tools)
    # 2. 调用模型并解析 JSON；无效则回退默认步骤
    try:
        msg = await chat.ainvoke([SystemMessage(content=sys), *list(chat_messages)])

        logger.warning(msg)
        
        content = getattr(msg, "content", None)
        text = content if isinstance(content, str) else str(content or "")
        data = _extract_json_object(text)
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
