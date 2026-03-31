"""OpenAI 兼容 Chat 客户端构造与密钥探测（规划、执行模块复用）。"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


def is_llm_configured(settings: Settings | None = None) -> bool:
    """是否配置了可用的 OpenAI 兼容密钥（非空字符串）。"""
    s = settings or get_settings()
    key = (s.openai_api_key or "").strip()
    return bool(key)


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """根据 Settings 构造 ChatOpenAI（base_url 可选）。"""
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
    }
    base = (settings.openai_api_base or "").strip()
    if base:
        kwargs["base_url"] = base
    return ChatOpenAI(**kwargs)
