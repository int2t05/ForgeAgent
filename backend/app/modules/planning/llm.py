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

logger = logging.getLogger(__name__)

_DEFAULT_STEPS: list[dict[str, Any]] = [
    {"id": "1", "title": "理解用户输入与上下文"},
    {"id": "2", "title": "按步执行并汇总结果"},
]


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


def _normalize_steps(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """校验步骤列表；可选 ``tool``、``args`` 供执行器调用（仅内置工具名有效）。"""
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
            row["tool"] = raw_tool.strip()
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
    本函数前置固定规划 ``SystemMessage``，与 LangChain Chat 模型调用约定一致。
    """
    s = settings or get_settings()
    # 1. 无 API 配置时直接使用内置默认计划
    if not is_llm_configured(s):
        return list(_DEFAULT_STEPS)

    chat = build_chat_model(s)
    sys = (
        "你是任务规划助手。根据用户与助手的前文对话及当前诉求，只输出一个 JSON 对象，不要 markdown 代码块。"
        '格式：{"steps":[{"id":"1","title":"步骤简述",'
        '"tool":"echo|mock_search（可选）","args":{...}（可选）},...]}。'
        "至少 1 个步骤，简单任务可只输出一步；title 用简短中文。"
        '需要向用户复述或确认时用 tool echo，args 示例：{"text":"..."}。'
        '需要占位检索时用 mock_search，args 可选 {"query":"关键词"}。'
        "分析与纯推理步骤可省略 tool。"
    )
    # 2. 调用模型并解析 JSON；无效则回退默认步骤
    try:
        msg = await chat.ainvoke([SystemMessage(content=sys), *list(chat_messages)])
        # logger.warning(msg)
        content = getattr(msg, "content", None)
        text = content if isinstance(content, str) else str(content or "")
        data = _extract_json_object(text)
        if data is None:
            logger.warning("planner LLM output not valid JSON, using default steps")
            return list(_DEFAULT_STEPS)
        normalized = _normalize_steps(data)
        if not normalized:
            logger.warning("planner LLM steps invalid, using default steps")
            return list(_DEFAULT_STEPS)
        return normalized
    except Exception:
        logger.exception("planner LLM call failed, using default steps")
        return list(_DEFAULT_STEPS)
