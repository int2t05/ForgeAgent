"""OpenAI 兼容 Chat 调用（规划 JSON、助手回复）；无密钥时由节点侧走内置逻辑。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_STEPS: list[dict[str, str]] = [
    {"id": "1", "title": "理解用户输入与上下文"},
    {"id": "2", "title": "按步执行并汇总结果"},
]


def is_llm_configured(settings: Settings | None = None) -> bool:
    """是否配置了可用的 OpenAI 兼容密钥（非空字符串）。"""
    s = settings or get_settings()
    key = (s.openai_api_key or "").strip()
    return bool(key)


def _build_chat_model(settings: Settings) -> ChatOpenAI:
    """根据 Settings 构造 ChatOpenAI（base_url 可选）。"""
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
    }
    base = (settings.openai_api_base or "").strip()
    if base:
        kwargs["base_url"] = base
    return ChatOpenAI(**kwargs)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中尽量解析出 JSON 对象。"""
    raw = text.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        data = json.loads(m.group())
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_steps(data: dict[str, Any]) -> list[dict[str, str]] | None:
    """校验并规范化 steps 列表；至少 2 步且含 id/title。"""
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

    chat = _build_chat_model(s)
    sys = (
        "你是任务规划助手。根据用户输入，只输出一个 JSON 对象，不要 markdown 代码块。"
        '格式：{"steps":[{"id":"1","title":"步骤标题"},...]}。'
        "至少 2 个步骤，title 用简短中文。"
    )
    try:
        # 调用 LLM 并提取 JSON
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


async def assistant_reply_with_llm(
    user_message: str,
    plan_steps: list[dict[str, str]],
    settings: Settings | None = None,
) -> str | None:
    """生成对用户的自然语言回复；失败返回 None（由调用方使用兜底文案）。"""
    s = settings or get_settings()
    if not is_llm_configured(s):
        return None

    chat = _build_chat_model(s)
    plan_text = json.dumps(plan_steps, ensure_ascii=False)
    sys = "你是 ForgeAgent 助手。根据用户问题与已执行计划，用简洁、友好的中文直接回答用户。"
    human = f"用户问题：{user_message}\n计划步骤概要：{plan_text}\n请给出最终回复（纯文本）。"
    try:
        msg = await chat.ainvoke(
            [SystemMessage(content=sys), HumanMessage(content=human)]
        )
        content = getattr(msg, "content", None)
        text = (content if isinstance(content, str) else str(content or "")).strip()
        return text or None
    except Exception:
        logger.exception("assistant LLM call failed")
        return None
