"""基于 LLM 的计划步骤生成与 JSON 解析（无密钥时回退默认步骤）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured

logger = logging.getLogger(__name__)

_DEFAULT_STEPS: list[dict[str, str]] = [
    {"id": "1", "title": "理解用户输入与上下文"},
    {"id": "2", "title": "按步执行并汇总结果"},
]


def _strip_markdown_json_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    t = re.sub(r"^```(?:json)?\s*", "", t, count=1, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
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


def _normalize_steps(data: dict[str, Any]) -> list[dict[str, str]] | None:
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        return None
    out: list[dict[str, str]] = []
    for i, item in enumerate(steps):
        if not isinstance(item, dict):
            return None
        sid = str(item.get("id") or str(i + 1))
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        out.append({"id": sid, "title": title.strip()})
    return out


async def plan_steps_with_llm(
    user_message: str, settings: Settings | None = None
) -> list[dict[str, str]]:
    """调用 LLM 生成计划步骤；失败时返回内置默认两步。"""
    s = settings or get_settings()
    if not is_llm_configured(s):
        return list(_DEFAULT_STEPS)

    chat = build_chat_model(s)
    sys = (
        "你是任务规划助手。根据用户输入，只输出一个 JSON 对象，不要 markdown 代码块。"
        '格式：{"steps":[{"id":"1","title":"步骤标题"},...]}。'
        "至少 2 个步骤，title 用简短中文。"
    )
    try:
        msg = await chat.ainvoke(
            [SystemMessage(content=sys), HumanMessage(content=user_message)]
        )
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
