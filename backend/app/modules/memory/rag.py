"""RAG 知识库：文档分块、向量化、混合检索（向量+BM25）和 Rerank 重排序。

基于 LangChain LCEL 构建 RAG Chain，支持：
- 文档分块（RecursiveCharacterTextSplitter）
- 向量化（OpenAI Embeddings 或本地 embeddings）
- 混合检索（向量 + BM25）
- Rerank 重排序

使用方式：
  from app.modules.memory.rag import RagKnowledgeBase, get_rag_chain
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnablePassthrough
from langchain_core.vectorstores import VectorStore

logger = logging.getLogger(__name__)

# ============================================================================
# Document Chunking
# ============================================================================


@dataclass
class ChunkConfig:
    """文档分块配置。"""
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: list[str] = field(default_factory=lambda: ["\n\n", "\n", "。", "！", "？", " ", ""])


def chunk_documents(
    documents: list[Document],
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    separators: list[str] | None = None,
) -> list[Document]:
    """将文档列表分块为较小的文本片段。

    使用递归字符分割器，按顺序尝试不同的分隔符。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    sep_list = separators or ["\n\n", "\n", "。", "！", "？", " ", ""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=sep_list,
        length_function=len,
    )
    return splitter.split_documents(documents)


def chunk_text(
    text: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    separators: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Document]:
    """将纯文本分块为文档列表。"""
    sep_list = separators or ["\n\n", "\n", "。", "！", "？", " ", ""]
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=sep_list,
        length_function=len,
    )
    docs = splitter.split_text(text)
    meta = metadata or {}
    return [Document(page_content=d, metadata=dict(meta)) for d in docs]


# ============================================================================
# Embeddings
# ============================================================================


class FakeEmbeddings(Embeddings):
    """本地伪嵌入（用于测试或无外部 API 时）。

    实际生产应使用 OpenAIEmbeddings 或本地 embeddings 模型。
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """生成伪嵌入向量。"""
        import hashlib

        vectors = []
        for text in texts:
            # 使用文本哈希生成确定性伪向量
            h = hashlib.sha256(text.encode()).digest()
            # 转换为固定维度的归一化向量
            vec = list(b / 255.0 for b in h[:256])
            # 补零到 256 维
            vec.extend([0.0] * (256 - len(vec)))
            vectors.append(vec)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """生成查询嵌入。"""
        return self.embed_documents([text])[0]


def create_embeddings(
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> Embeddings:
    """创建嵌入模型实例。

    优先使用 OpenAI Embeddings，失败时回退到本地 FakeEmbeddings。
    """
    try:
        from langchain_openai import OpenAIEmbeddings

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        if model:
            kwargs["model"] = model
        return OpenAIEmbeddings(**kwargs)
    except ImportError:
        logger.warning("langchain-openai 未安装，回退到 FakeEmbeddings")
        return FakeEmbeddings()
    except Exception as e:
        logger.warning("创建 OpenAI Embeddings 失败，回退到 FakeEmbeddings: %s", e)
        return FakeEmbeddings()


# ============================================================================
# Vector Store
# ============================================================================


def create_vector_store(
    embedding: Embeddings | None = None,
    *,
    persist_directory: str | None = None,
) -> VectorStore:
    """创建向量存储。

    优先使用 ChromaDB（支持混合检索），其次 FAISS。
    """
    emb = embedding or create_embeddings()

    # ChromaDB
    try:
        import chromadb
        from langchain_chroma import Chroma

        coll_name = "forgeagent_rag"
        if persist_directory:
            Path(persist_directory).mkdir(parents=True, exist_ok=True)
            return Chroma(
                embedding_function=emb,
                persist_directory=persist_directory,
                collection_name=coll_name,
            )
        else:
            return Chroma(embedding_function=emb, collection_name=coll_name)
    except ImportError:
        logger.warning("langchain-chroma 未安装，尝试使用 FAISS")
    except Exception as e:
        logger.warning("ChromaDB 初始化失败，尝试 FAISS: %s", e)

    # FAISS fallback
    try:
        from langchain_community.vectorstores import FAISS

        return FAISS(embedding_function=emb)
    except ImportError:
        raise RuntimeError(
            "请安装向量存储依赖: pip install langchain-chroma faiss-cpu"
        )


# ============================================================================
# BM25 Retriever (for hybrid search)
# ============================================================================


class BM25Retriever:
    """BM25 关键字检索器，用于混合检索。

    基于 rank_bm25 库实现。
    """

    def __init__(self, documents: list[Document] | None = None):
        self._docs: list[Document] = documents or []
        self._tokenized_docs: list[list[str]] = []
        self._scores: list[float] = []
        self._initialized = False

    def add_documents(self, documents: list[Document]) -> None:
        """添加文档到索引。"""
        self._docs.extend(documents)
        self._tokenized_docs = [
            self._tokenize(doc.page_content) for doc in self._docs
        ]
        self._initialized = False

    def _tokenize(self, text: str) -> list[str]:
        """简单分词。"""
        # 移除特殊字符，小写化，按空白符分割
        text = re.sub(r"[^\w\s]", " ", text.lower())
        return text.split()

    def _calculate_bm25(
        self, query: str, k1: float = 1.5, b: float = 0.75
    ) -> list[tuple[int, float]]:
        """计算 BM25 分数。"""
        if not self._tokenized_docs:
            return []

        # 计算平均文档长度
        avg_dl = sum(len(tokens) for tokens in self._tokenized_docs) / len(
            self._tokenized_docs
        )
        if avg_dl == 0:
            avg_dl = 1

        query_tokens = self._tokenize(query)
        doc_scores: list[tuple[int, float]] = []

        N = len(self._tokenized_docs)

        # 计算每个词的出现文档数
        doc_freq: dict[str, int] = {}
        for tokens in self._tokenized_docs:
            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1

        for idx, tokens in enumerate(self._tokenized_docs):
            score = 0.0
            dl = len(tokens)
            token_set = set(tokens)
            token_counts: dict[str, int] = {}
            for t in tokens:
                token_counts[t] = token_counts.get(t, 0) + 1

            for qt in query_tokens:
                if qt not in token_set:
                    continue
                df = doc_freq.get(qt, 0)
                if df == 0:
                    continue
                tf = token_counts.get(qt, 0)
                # BM25 公式
                idf = max(0.1, (N - df + 0.5) / (df + 0.5))
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / avg_dl)
                score += idf * numerator / denominator
            doc_scores.append((idx, score))

        # 按分数降序
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        return doc_scores

    def invoke(self, query: str, *, top_k: int = 5) -> list[Document]:
        """检索相关文档。"""
        if not self._docs:
            return []

        scores = self._calculate_bm25(query)
        results = []
        seen = set()
        for idx, score in scores:
            if idx in seen:
                continue
            seen.add(idx)
            doc = self._docs[idx]
            doc.metadata["bm25_score"] = score
            results.append(doc)
            if len(results) >= top_k:
                break
        return results


# ============================================================================
# Reranker
# ============================================================================


def create_reranker(
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    top_n: int = 5,
):
    """创建重排序器。

    使用 Cohere 或本地交叉编码器进行 Rerank。
    """
    # Cohere Rerank
    try:
        from langchain_community.cross_imports import CohereRerank

        kwargs: dict[str, Any] = {"top_n": top_n}
        if api_key:
            kwargs["cohere_api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        if model:
            kwargs["model"] = model
        return CohereRerank(**kwargs)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Cohere Rerank 初始化失败: %s", e)

    # 本地 MiniLM rerank (sentence-transformers)
    try:
        from langchain_community.cross_imports import SentenceTransformerRerank

        kwargs: dict[str, Any] = {"top_n": top_n}
        if model:
            kwargs["model"] = model
        else:
            kwargs["model"] = "cross-encoder/ms-marco-MiniLM-L-12-v2"
        return SentenceTransformerRerank(**kwargs)
    except ImportError:
        logger.warning("sentence-transformers 未安装，跳过 Rerank")
    except Exception as e:
        logger.warning("本地 Rerank 初始化失败: %s", e)

    # 无 Rerank 时返回 None
    logger.info("未配置 Rerank 器，混合检索结果将不进行重排序")
    return None


class NoOpReranker:
    """无操作重排序器（透传）。"""

    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def invoke(self, documents: list[Document], **kwargs) -> list[Document]:
        return documents[: self.top_n]


# ============================================================================
# Hybrid Search (Vector + BM25)
# ============================================================================


@dataclass
class SearchResult:
    """检索结果。"""
    content: str
    metadata: dict[str, Any]
    score: float
    source: Literal["vector", "bm25", "rerank"]


class HybridSearch:
    """混合检索器：向量检索 + BM25 关键字检索 + Rerank。

    支持 reciprocal_rank_fusion 融合分数。
    """

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_retriever: BM25Retriever | None = None,
        reranker: Any = None,
        *,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
        fusion_k: int = 60,
    ):
        self.vector_store = vector_store
        self.bm25_retriever = bm25_retriever
        self.reranker = reranker
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.fusion_k = fusion_k

    @staticmethod
    def reciprocal_rank_fusion(
        rankings: list[list[tuple[int, float]]], k: int = 60
    ) -> list[tuple[int, float]]:
        """倒数排名融合（RRF）算法。

        用于合并多个检索结果。
        """
        scores: dict[int, float] = {}
        for ranking in rankings:
            for rank, (doc_id, score) in enumerate(ranking):
                if doc_id not in scores:
                    scores[doc_id] = 0.0
                scores[doc_id] += 1.0 / (k + rank + 1)

        result = [(doc_id, score) for doc_id, score in scores.items()]
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        vector_top_k: int | None = None,
        bm25_top_k: int | None = None,
        rerank_top_k: int | None = None,
    ) -> list[SearchResult]:
        """执行混合检索。"""
        v_top = vector_top_k or top_k * 2
        b_top = bm25_top_k or top_k * 2
        r_top = rerank_top_k or top_k

        all_results: dict[str, SearchResult] = {}

        # 向量检索
        try:
            vector_docs = self.vector_store.similarity_search_with_score(query, k=v_top)
            for doc, score in vector_docs:
                doc_id = self._doc_id(doc)
                all_results[doc_id] = SearchResult(
                    content=doc.page_content,
                    metadata=dict(doc.metadata),
                    score=score,
                    source="vector",
                )
        except Exception as e:
            logger.warning("向量检索失败: %s", e)

        # BM25 检索
        if self.bm25_retriever:
            try:
                bm25_docs = self.bm25_retriever.invoke(query, top_k=b_top)
                for doc in bm25_docs:
                    doc_id = self._doc_id(doc)
                    score = doc.metadata.get("bm25_score", 0.0)
                    if doc_id in all_results:
                        all_results[doc_id].score = (
                            self.vector_weight * all_results[doc_id].score
                            + self.bm25_weight * score
                        )
                    else:
                        all_results[doc_id] = SearchResult(
                            content=doc.page_content,
                            metadata=dict(doc.metadata),
                            score=score,
                            source="bm25",
                        )
            except Exception as e:
                logger.warning("BM25 检索失败: %s", e)

        # 如果没有 BM25，进行 RRF 融合
        if not self.bm25_retriever and len(all_results) > 1:
            # 构建假排名用于 RRF
            rankings: list[list[tuple[int, float]]] = []
            for idx, (doc_id, result) in enumerate(all_results.items()):
                # 使用负分数作为排名依据（越大越好）
                rankings.append([(idx, -result.score)])
            fused = self.reciprocal_rank_fusion(rankings, k=self.fusion_k)
            doc_ids = [doc_id for doc_id, _ in fused[:top_k]]
            reranked_results = {
                doc_id: all_results[doc_id] for doc_id in doc_ids if doc_id in all_results
            }
            all_results = reranked_results

        # Rerank
        if self.reranker and len(all_results) > r_top:
            try:
                docs_for_rerank = [
                    Document(page_content=r.content, metadata=r.metadata)
                    for r in all_results.values()
                ]
                reranked = self.reranker.invoke(docs_for_rerank, query=query)
                all_results = {}
                for doc in reranked:
                    doc_id = self._doc_id(doc)
                    if doc_id in all_results:
                        all_results[doc_id].source = "rerank"
                    else:
                        all_results[doc_id] = SearchResult(
                            content=doc.page_content,
                            metadata=dict(doc.metadata),
                            score=0.0,
                            source="rerank",
                        )
            except Exception as e:
                logger.warning("Rerank 失败: %s", e)

        # 转换为列表并截断
        results = list(all_results.values())
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _doc_id(doc: Document) -> str:
        """生成文档唯一 ID。"""
        content = doc.page_content
        meta_str = json.dumps(doc.metadata, sort_keys=True, ensure_ascii=False)
        return hashlib.md5((content + meta_str).encode()).hexdigest()


# ============================================================================
# RAG Knowledge Base (Main Class)
# ============================================================================


@dataclass
class RagConfig:
    """RAG 配置。"""
    persist_directory: str | None = None
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    reranker_model: str | None = None
    reranker_api_key: str | None = None
    reranker_base_url: str | None = None
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    default_top_k: int = 5


class RagKnowledgeBase:
    """RAG 知识库管理器。

    支持：
    - 文档摄入（分块、向量化、存储）
    - 混合检索（向量 + BM25 + Rerank）
    - 持久化
    """

    def __init__(self, config: RagConfig | None = None):
        self.config = config or RagConfig()
        self._embeddings: Embeddings | None = None
        self._vector_store: VectorStore | None = None
        self._bm25_retriever: BM25Retriever | None = None
        self._reranker: Any = None
        self._hybrid_search: HybridSearch | None = None
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    def embeddings(self) -> Embeddings:
        """获取或创建嵌入模型。"""
        if self._embeddings is None:
            self._embeddings = create_embeddings(
                model=self.config.embedding_model,
                api_key=self.config.embedding_api_key,
                base_url=self.config.embedding_base_url,
            )
        return self._embeddings

    @property
    def vector_store(self) -> VectorStore:
        """获取或创建向量存储。"""
        if self._vector_store is None:
            self._vector_store = create_vector_store(
                embedding=self.embeddings,
                persist_directory=self.config.persist_directory,
            )
        return self._vector_store

    @property
    def bm25_retriever(self) -> BM25Retriever:
        """获取或创建 BM25 检索器。"""
        if self._bm25_retriever is None:
            self._bm25_retriever = BM25Retriever()
        return self._bm25_retriever

    @property
    def reranker(self) -> Any:
        """获取或创建重排序器。"""
        if self._reranker is None:
            self._reranker = create_reranker(
                model=self.config.reranker_model,
                api_key=self.config.reranker_api_key,
                base_url=self.config.reranker_base_url,
                top_n=self.config.default_top_k,
            )
            if self._reranker is None:
                self._reranker = NoOpReranker(top_n=self.config.default_top_k)
        return self._reranker

    @property
    def hybrid_search(self) -> HybridSearch:
        """获取或创建混合检索器。"""
        if self._hybrid_search is None:
            self._hybrid_search = HybridSearch(
                vector_store=self.vector_store,
                bm25_retriever=self.bm25_retriever,
                reranker=self.reranker,
                vector_weight=self.config.vector_weight,
                bm25_weight=self.config.bm25_weight,
            )
        return self._hybrid_search

    def initialize(self) -> None:
        """同步初始化。"""
        if self._initialized:
            return
        # 触发各属性的延迟初始化
        _ = self.embeddings
        _ = self.vector_store
        _ = self.bm25_retriever
        _ = self.reranker
        _ = self.hybrid_search
        self._initialized = True

    async def ainitialize(self) -> None:
        """异步初始化。"""
        async with self._lock:
            if not self._initialized:
                await asyncio.to_thread(self.initialize)

    def ingest_text(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        """摄入纯文本到知识库。返回分块数量。"""
        chunk_size = chunk_size or self.config.chunk_size
        chunk_overlap = chunk_overlap or self.config.chunk_overlap

        docs = chunk_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            metadata=metadata,
        )

        # 添加到向量存储
        self.vector_store.add_documents(docs)

        # 同步更新 BM25
        self.bm25_retriever.add_documents(docs)

        # 持久化（如果支持）
        self._persist_if_possible()

        logger.info("RAG 摄入文本，分块数: %d", len(docs))
        return len(docs)

    async def aingest_text(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        """异步摄入纯文本。"""
        return await asyncio.to_thread(
            self.ingest_text,
            text,
            metadata=metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def ingest_documents(
        self,
        documents: list[Document],
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        """摄入文档列表。返回分块数量。"""
        chunk_size = chunk_size or self.config.chunk_size
        chunk_overlap = chunk_overlap or self.config.chunk_overlap

        docs = chunk_documents(
            documents,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        self.vector_store.add_documents(docs)
        self.bm25_retriever.add_documents(docs)
        self._persist_if_possible()

        logger.info("RAG 摄入文档，分块数: %d", len(docs))
        return len(docs)

    async def aingest_documents(
        self,
        documents: list[Document],
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        """异步摄入文档。"""
        return await asyncio.to_thread(
            self.ingest_documents,
            documents,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """检索知识库。"""
        k = top_k or self.config.default_top_k
        results = self.hybrid_search.search(query, top_k=k)
        logger.debug("RAG 检索 query='%s' 返回 %d 条结果", query, len(results))
        return results

    async def asearch(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """异步检索知识库。"""
        return await asyncio.to_thread(self.search, query, top_k=top_k)

    def _persist_if_possible(self) -> None:
        """持久化向量存储（如果支持）。"""
        try:
            vs = self._vector_store
            if vs is not None and hasattr(vs, "persist"):
                vs.persist()
        except Exception as e:
            logger.warning("向量存储持久化失败: %s", e)

    def get_retriever(self, **kwargs):
        """获取 LangChain Retriever 接口（用于 LCEL RAG Chain）。"""
        return self.vector_store.as_retriever(**kwargs)


# ============================================================================
# RAG Chain (LCEL)
# ============================================================================


def get_rag_chain(
    rag: RagKnowledgeBase,
    llm: Any,
    *,
    system_prompt: str | None = None,
) -> Any:
    """构建 LCEL RAG Chain。

    示例：
        from app.modules.memory.rag import get_rag_chain, RagKnowledgeBase
        from app.core.llm_openai import build_chat_model
        from app.core.config import get_settings

        rag = RagKnowledgeBase(RagConfig(persist_directory="./db_rag"))
        settings = get_settings()
        llm = build_chat_model(settings)
        chain = get_rag_chain(rag, llm)

        result = await chain.ainvoke({"question": "什么是 ForgeAgent？"})
    """
    from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
    from langchain_core.runnables import RunnablePassthrough

    # 默认系统提示
    default_system = (
        "你是一个有用的助手。基于以下检索到的上下文来回答用户的问题。\n"
        "如果上下文中没有相关信息，请说明你不知道，不要编造答案。\n\n"
        "上下文：\n{context}"
    )

    # 检索格式
    def format_docs(docs: list) -> str:
        return "\n\n".join(doc.page_content for doc in docs)

    # 构建 Chain
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt or default_system),
        ("human", "{question}"),
    ])

    rag_chain = (
        {"context": rag.get_retriever() | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
    )

    return rag_chain


# ============================================================================
# Global RAG Instance
# ============================================================================

_global_rag: RagKnowledgeBase | None = None
_rag_lock = asyncio.Lock()


async def get_global_rag(
    persist_directory: str | None = None,
    **kwargs,
) -> RagKnowledgeBase:
    """获取全局 RAG 实例（单例）。"""
    global _global_rag
    async with _rag_lock:
        if _global_rag is None:
            config = RagConfig(persist_directory=persist_directory, **kwargs)
            _global_rag = RagKnowledgeBase(config)
            await _global_rag.ainitialize()
        return _global_rag


def reset_global_rag() -> None:
    """重置全局 RAG 实例（测试用）。"""
    global _global_rag
    _global_rag = None
