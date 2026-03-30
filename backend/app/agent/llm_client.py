"""OpenAI 兼容 Chat 调用（规划 JSON、助手回复）；无密钥时由节点侧走内置逻辑。"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
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


def _strip_markdown_json_fence(text: str) -> str:
    """去掉可选的 ``` / ```json 代码块包裹，降低模型违规包 fence 时的失败率。"""
    t = text.strip()
    if not t.startswith("```"):
        return t
    # 去掉起始 ``` 或 ```json
    t = re.sub(r"^```(?:json)?\s*", "", t, count=1, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中尽量解析出 JSON 对象。

    不用贪心正则 ``\\{[\\s\\S]*\\}``：模型在 JSON 后若附带含 ``}`` 的说明，
    会截到过宽片段导致 ``json.loads`` 失败（表现为时好时坏）。
    改为对每个 ``{`` 起调用 ``JSONDecoder.raw_decode``，取第一个成功解析的 dict。
    """
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


def _chunk_text_content(chunk: Any) -> str:
    """获取 chunk 的文本内容"""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return str(content or "")


async def assistant_reply_stream_with_llm(
    user_message: str,
    plan_steps: list[dict[str, str]],
    settings: Settings | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """获取 LLM 的回复"""
    from app.agent.llm_stream_split import ThinkAnswerStream

    s = settings or get_settings()
    splitter = ThinkAnswerStream()
    plan_text = json.dumps(plan_steps, ensure_ascii=False)
    sys_stream = "你是 ForgeAgent 助手。结合用户问题与下列计划，用中文直接回答。"
    human_stream = f"用户问题：{user_message}\n计划步骤：{plan_text}"

    if not is_llm_configured(s):
        ans = "任务已完成（LangGraph 最小闭环）。配置 API Key 后可使用完整模型。\n"
        for i in range(0, len(ans), 4):
            for phase, delta in splitter.feed(ans[i : i + 4]):
                yield phase, delta
        for phase, delta in splitter.finalize():
            yield phase, delta
        return

    chat = _build_chat_model(s)
    try:
        async for chunk in chat.astream(
            [SystemMessage(content=sys_stream), HumanMessage(content=human_stream)]
        ):
            text = _chunk_text_content(chunk)
            if not text:
                continue
            for phase, delta in splitter.feed(text):
                yield phase, delta
        for phase, delta in splitter.finalize():
            yield phase, delta
    except Exception:
        logger.exception("assistant LLM stream failed")
        for phase, delta in splitter.finalize():
            yield phase, delta
