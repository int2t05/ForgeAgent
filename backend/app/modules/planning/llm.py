"""规划 LLM：由 ``BaseMessage`` 序列生成抽象 ``plan_steps``（目标级描述，不含工具名）。

输出经 JSON 解析与规范化；无密钥或非法结构时回退内置双步计划。工具目录仅在执行侧注入。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.config import Settings, get_settings
from app.core.llm_openai import build_chat_model, is_llm_configured
from app.core.llm_retry import ainvoke_with_retry
from app.modules.prompts import (
    RETRY_PLANNER,
    RETRY_SKILL_SELECTOR,
    build_planner_prompt,
    build_skill_selector_prompt,
)
from app.modules.tools.skill_sources import resolve_planner_skill_imports
from app.shared.langchain_content import message_content_text
from app.shared.llm_json_parse import parse_llm_json_object

logger = logging.getLogger(__name__)

_DEFAULT_SKILL_SELECTOR_MAX_ATTEMPTS = 2


async def select_skills_for_planner(
    chat_messages: Sequence[BaseMessage],
    settings: Settings | None = None,
    *,
    configured_skill_paths: list[str],
) -> list[str]:
    """询问 LLM 哪些 Skill 目录相关，并解析为真实路径。

    返回已解析的绝对路径列表；无相关目录或 LLM 未配置时返回空列表。
    """
    if not configured_skill_paths:
        return []

    s = settings or get_settings()
    if not is_llm_configured(s):
        return []

    chat = build_chat_model(s)
    sys_prompt = build_skill_selector_prompt(list(configured_skill_paths))
    messages: list[BaseMessage] = [
        SystemMessage(content=sys_prompt),
        *list(chat_messages),
    ]

    max_attempts = max(1, _DEFAULT_SKILL_SELECTOR_MAX_ATTEMPTS)
    for attempt in range(max_attempts):
        try:
            msg = await ainvoke_with_retry(chat, messages, s)
        except Exception:
            logger.exception(
                "skill selector LLM call failed (attempt %s/%s)",
                attempt + 1,
                max_attempts,
            )
            break

        text = message_content_text(msg)
        data = parse_llm_json_object(text)
        if data is None:
            logger.warning(
                "skill selector output not valid JSON (attempt %s/%s)",
                attempt + 1,
                max_attempts,
            )
            if attempt < max_attempts - 1:
                messages.append(msg)
                messages.append(HumanMessage(content=RETRY_SKILL_SELECTOR))
            continue

        raw = data.get("skill_imports")
        if not isinstance(raw, list):
            logger.warning(
                "skill selector returned non-list skill_imports; ignoring",
            )
            break

        resolved = resolve_planner_skill_imports(
            [str(x) for x in raw if isinstance(x, str)],
            configured_skill_paths,
        )
        logger.info(
            "skill selector selected: %s (raw=%s)",
            resolved,
            raw,
        )
        return resolved

    logger.warning("skill selector exhausted attempts; returning empty list")
    return []


_DEFAULT_STEPS: list[dict[str, Any]] = [
    {
        "id": "1",
        "title": "理解用户输入与上下文",
        "description": "澄清目标、约束与已知事实",
    },
    {
        "id": "2",
        "title": "执行并汇总",
        "description": "按计划逐步达成子目标并在最后整合结论",
    },
]


_FORBIDDEN_PLAN_KEYS = frozenset(
    {
        "tool",
        "args",
        "tool_name",
        "function",
        "function_call",
        "action",
    }
)


def _normalize_steps(
    data: dict[str, Any],
    *,
    configured_skill_paths: list[str],
) -> list[dict[str, Any]] | None:
    """将模型根对象中的 ``steps`` 转为可入库行集；剔除禁止的工具相关键；校验 ``skill_imports``。"""
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) < 1:
        return None
    cfg = configured_skill_paths or []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(steps):
        if not isinstance(item, dict):
            return None
        leaked = _FORBIDDEN_PLAN_KEYS.intersection(item.keys())
        if leaked:
            logger.warning(
                "planner step contained forbidden keys %s; stripped from normalized plan",
                sorted(leaked),
            )
        sid = str(item.get("id") or str(i + 1))
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        row: dict[str, Any] = {"id": sid, "title": title.strip()}
        for meta_key in ("goal", "description", "expected_output"):
            mv = item.get(meta_key)
            if isinstance(mv, str) and mv.strip():
                row[meta_key] = mv.strip()
        raw_skills = item.get("skill_imports")
        if raw_skills is not None:
            if not isinstance(raw_skills, list):
                logger.warning(
                    "planner step %s skill_imports invalid type, omitted",
                    sid,
                )
            elif cfg:
                resolved = resolve_planner_skill_imports(
                    [str(x) for x in raw_skills if x is not None],
                    cfg,
                )
                if resolved:
                    row["skill_imports"] = resolved
            elif raw_skills:
                logger.warning(
                    "planner emitted skill_imports but no skill directories configured; omitted",
                )
        out.append(row)
    return out


async def plan_steps_with_llm(
    chat_messages: Sequence[BaseMessage],
    settings: Settings | None = None,
    *,
    configured_skill_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    """异步请求规划模型并返回规范化步骤列表；失败路径返回内置默认。"""
    s = settings or get_settings()
    skill_paths = list(configured_skill_paths or [])
    # 1. LLM 未配置：直接内置计划
    if not is_llm_configured(s):
        return list(_DEFAULT_STEPS)

    chat = build_chat_model(s)
    sys = build_planner_prompt(skill_paths)
    messages: list[BaseMessage] = [SystemMessage(content=sys), *list(chat_messages)]
    max_rounds = max(1, int(s.planner_parse_max_attempts))
    # 2. 调用模型、解析 JSON、规范化；解析或结构失败时可多轮重试（附上上一轮输出与纠偏提示）
    for attempt in range(max_rounds):
        try:
            msg = await ainvoke_with_retry(chat, messages, s)
        except Exception:
            logger.exception(
                "planner LLM call failed (attempt %s/%s)",
                attempt + 1,
                max_rounds,
            )
            if attempt >= max_rounds - 1:
                return list(_DEFAULT_STEPS)
            continue

        text = message_content_text(msg)
        data = parse_llm_json_object(text)
        if data is None:
            logger.warning(
                "planner LLM output not valid JSON (attempt %s/%s)",
                attempt + 1,
                max_rounds,
            )
            if attempt < max_rounds - 1:
                messages.append(msg)
                messages.append(HumanMessage(content=RETRY_PLANNER))
            continue

        normalized = _normalize_steps(data, configured_skill_paths=skill_paths)
        if not normalized:
            logger.warning(
                "planner LLM steps invalid (attempt %s/%s)",
                attempt + 1,
                max_rounds,
            )
            if attempt < max_rounds - 1:
                messages.append(msg)
                messages.append(HumanMessage(content=RETRY_PLANNER))
            continue

        return normalized

    logger.warning(
        "planner exhausted %s parse/validation attempt(s), using default steps",
        max_rounds,
    )
    return list(_DEFAULT_STEPS)
