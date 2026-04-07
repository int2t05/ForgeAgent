"""RAG 知识库与 Agent 工作流融合。

将 RAG 检索结果自动注入到 Planner 上下文，使 Agent 能够：
1. 在规划阶段自动检索相关知识
2. 基于检索结果生成更准确的计划
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# RAG 检索结果的最大 token 估算（用于判断是否注入）
_RAG_CONTEXT_MAX_CHARS = 4000


def _format_rag_results_for_context(
    results: list, *, include_source: bool = True
) -> str:
    """将 RAG 检索结果格式化为可注入上下文的文本。"""
    if not results:
        return ""

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        content = r.content if hasattr(r, "content") else str(r)
        if include_source:
            source = r.metadata.get("source", "unknown") if hasattr(r, "metadata") else "unknown"
            parts.append(f"[文档{i}] 来源: {source}\n{content}")
        else:
            parts.append(f"[文档{i}]\n{content}")

    return "\n\n".join(parts)


async def retrieve_rag_context(
    query: str,
    *,
    settings: Settings | None = None,
    top_k: int | None = None,
) -> str:
    """从 RAG 知识库检索相关内容并格式化为上下文文本。

    Args:
        query: 检索查询
        settings: 配置对象
        top_k: 返回结果数量

    Returns:
        格式化后的 RAG 上下文文本，如果没有结果则返回空字符串
    """
    s = settings or get_settings()

    if not s.rag_enabled:
        return ""

    try:
        from app.modules.memory.rag import RagKnowledgeBase, RagConfig

        config = RagConfig(
            persist_directory=s.rag_persist_directory,
            chunk_size=s.rag_chunk_size,
            chunk_overlap=s.rag_chunk_overlap,
            embedding_model=s.rag_embedding_model,
            embedding_api_key=s.rag_embedding_api_key,
            embedding_base_url=s.rag_embedding_base_url,
            reranker_model=s.rag_reranker_model,
            reranker_api_key=s.rag_reranker_api_key,
            reranker_base_url=s.rag_reranker_base_url,
            vector_weight=s.rag_vector_weight,
            bm25_weight=s.rag_bm25_weight,
            default_top_k=top_k or s.rag_default_top_k,
        )
        rag = RagKnowledgeBase(config)
        rag.initialize()

        results = rag.search(query, top_k=top_k or s.rag_default_top_k)
        if not results:
            logger.debug("RAG 检索无结果: query=%s", query)
            return ""

        formatted = _format_rag_results_for_context(results)
        if len(formatted) > _RAG_CONTEXT_MAX_CHARS:
            formatted = formatted[:_RAG_CONTEXT_MAX_CHARS] + "\n[... 已截断 ...]"

        logger.info(
            "RAG 检索成功: query=%s, results=%d, context_chars=%d",
            query,
            len(results),
            len(formatted),
        )
        return formatted

    except Exception as e:
        logger.warning("RAG 检索失败: query=%s, error=%s", query, e)
        return ""


async def build_rag_context_for_planner(
    user_message: str,
    *,
    settings: Settings | None = None,
    rag_top_k: int | None = None,
    include_rag: bool = True,
) -> list[HumanMessage]:
    """为 Planner 构建 RAG 上下文消息。

    在用户消息基础上进行 RAG 检索，将相关文档作为独立的 HumanMessage 注入。

    Args:
        user_message: 用户消息（用作检索 query）
        settings: 配置对象
        rag_top_k: RAG 返回数量
        include_rag: 是否执行 RAG 检索

    Returns:
        HumanMessage 列表（包含 RAG 上下文）
    """
    messages: list[HumanMessage] = []
    s = settings or get_settings()

    if not include_rag or not s.rag_enabled:
        return messages

    rag_context = await retrieve_rag_context(
        user_message,
        settings=s,
        top_k=rag_top_k,
    )

    if rag_context:
        messages.append(
            HumanMessage(
                content=f"【RAG 知识库检索结果】\n\n{rag_context}"
            )
        )

    return messages


def inject_rag_context_into_messages(
    messages: list,
    rag_context: str,
) -> list:
    """将 RAG 上下文注入到消息列表中。

    RAG 上下文插入在用户消息之后、规划 LLM 调用之前。
    插入位置：系统消息之后，第一个用户消息之后。

    Args:
        messages: 原始消息列表
        rag_context: RAG 上下文文本

    Returns:
        注入了 RAG 上下文的消息列表
    """
    if not rag_context:
        return messages

    from langchain_core.messages import HumanMessage, SystemMessage

    rag_msg = HumanMessage(content=f"【RAG 知识库参考】\n\n{rag_context}")

    # 找到第一个非 SystemMessage 的位置插入
    for i, msg in enumerate(messages):
        if not isinstance(msg, SystemMessage):
            return messages[:i] + [rag_msg] + messages[i:]

    # 如果全是 SystemMessage，追加到末尾
    return messages + [rag_msg]
