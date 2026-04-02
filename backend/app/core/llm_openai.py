"""OpenAI 兼容 Chat 客户端。

提供密钥探测与基于进程配置的 ChatOpenAI 构造，供规划、路由、ReAct、流式总结等模块复用；
输入长度由 ``app.core.llm_retry`` 内统一预算裁剪。
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


def is_llm_configured(settings: Settings | None = None) -> bool:
    """判断是否存在非空的 OpenAI 兼容 API Key 配置。"""
    s = settings or get_settings()
    key = (s.openai_api_key or "").strip()
    return bool(key)


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """按 Settings 构造带 base_url、超时与 SDK 重试的 ChatOpenAI 实例。"""
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
        "max_retries": max(0, int(settings.openai_max_retries)),
    }
    base = (settings.openai_api_base or "").strip()
    if base:
        kwargs["base_url"] = base
    # 显式 request_timeout：避免上游永久 pending 表现为「后端卡死」
    if float(settings.openai_request_timeout) > 0:
        kwargs["request_timeout"] = float(settings.openai_request_timeout)
    return ChatOpenAI(**kwargs)
