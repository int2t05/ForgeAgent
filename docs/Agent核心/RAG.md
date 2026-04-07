# RAG 知识库

## 概述

RAG（Retrieval-Augmented Generation）知识库为 ForgeAgent 提供持久化知识检索能力，使 Agent 能够基于文档内容回答问题。

## 与 Agent 工作流融合

RAG 知识库通过两种方式融入 Agent 工作流：

### 1. 隐式融合（自动注入到 Planner）

在 **Plan 节点**自动检索 RAG 知识库，将相关文档注入规划上下文：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Plan 节点                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 加载会话历史消息                                             │
│           ↓                                                      │
│  2. 【自动 RAG 检索】 ← 基于用户消息查询知识库                     │
│           ↓                                                      │
│  3. 注入检索结果到上下文                                         │
│           ↓                                                      │
│  4. 选择相关 Skill（如有）                                       │
│           ↓                                                      │
│  5. 读取黑板要点                                                │
│           ↓                                                      │
│  6. 调用 LLM 生成计划步骤                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**代码位置**：`app/modules/planning/nodes.py`

```python
# 在 plan_node 中自动检索 RAG
rag_messages = await build_rag_context_for_planner(
    user_message,
    settings=settings,
)
chat_messages.extend(rag_messages)
```

### 2. 显式调用（Agent 工具调用）

Agent 在执行过程中**显式调用** `rag_search` 工具：

```
Actor 执行节点：
  step_react_loop
      ↓
  LLM 判断：需要查询知识库
      ↓
  调用 rag_search 工具 ← Agent 显式触发
      ↓
  检索结果作为 Observation 注入
```

**使用场景**：
- Agent 发现知识不足，主动检索
- 需要查询特定文档内容
- 实时性要求高的检索

### 3. 混合策略（推荐）

```
Plan 阶段：自动注入 RAG 上下文（确保规划有基础背景知识）
     ↓
Act 阶段：Agent 可显式调用 rag_search（如需更精确检索）
     ↓
Learn 阶段：反思检索结果，更新黑板
```

## 使用示例

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     RAG Knowledge Base                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Document   │  │   Embedding  │  │  Vector Store │          │
│  │  Ingestion   │─▶│   Model      │─▶│  (Chroma/FAISS)│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                                       │               │
│         ▼                                       ▼               │
│  ┌──────────────┐                       ┌──────────────┐       │
│  │   Text       │                       │    Hybrid    │       │
│  │  Chunking    │                       │    Search    │       │
│  └──────────────┘                       └──────┬───────┘       │
│                                                │               │
│                                                ▼               │
│                                         ┌──────────────┐       │
│                                         │    Rerank    │       │
│                                         │  (Cohere/    │       │
│                                         │   CrossEnc.) │       │
│                                         └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. 文档分块 (Text Chunking)

使用 `RecursiveCharacterTextSplitter` 按优先级尝试不同分隔符：

```python
from app.modules.memory.rag import chunk_text

docs = chunk_text(
    "长文本内容...",
    chunk_size=500,      # 每块最大字符数
    chunk_overlap=50,     # 块之间重叠字符数
    separators=["\n\n", "\n", "。", "！", "？", " ", ""]
)
```

### 2. 向量化 (Embedding)

支持多种嵌入模型：

```python
from app.modules.memory.rag import create_embeddings

# OpenAI Embeddings
emb = create_embeddings(
    model="text-embedding-3-small",
    api_key="sk-...",
    base_url="https://api.openai.com/v1"
)

# 本地伪嵌入（测试用）
from app.modules.memory.rag import FakeEmbeddings
emb = FakeEmbeddings()
```

### 3. 向量存储 (Vector Store)

```python
from app.modules.memory.rag import create_vector_store

# ChromaDB（推荐）
vs = create_vector_store(
    embedding=emb,
    persist_directory="./db_rag"
)

# FAISS fallback
from langchain_community.vectorstores import FAISS
vs = FAISS(embedding_function=emb)
```

### 4. 混合检索 (Hybrid Search)

结合向量检索和 BM25 关键字检索：

```python
from app.modules.memory.rag import HybridSearch, BM25Retriever

search = HybridSearch(
    vector_store=vs,
    bm25_retriever=BM25Retriever(),
    reranker=reranker,  # 可选
    vector_weight=0.5,
    bm25_weight=0.5,
)

results = search.search("查询语句", top_k=10)
```

### 5. Rerank 重排序

使用交叉编码器对检索结果进行重排序：

```python
from app.modules.memory.rag import create_reranker

# Cohere Rerank
reranker = create_reranker(
    model="rerank-multilingual-v2.0",
    api_key="...",
    top_n=5
)

# 本地 MiniLM
from langchain_community.cross_imports import SentenceTransformerRerank
reranker = SentenceTransformerRerank(
    model="cross-encoder/ms-marco-MiniLM-L-12-v2",
    top_n=5
)
```

## RAG 工具

### rag_search

在知识库中检索相关内容：

```json
{
  "tool": "rag_search",
  "args": {
    "query": "ForgeAgent 是什么？",
    "top_k": 5,
    "include_scores": true
  }
}
```

返回：

```json
{
  "ok": true,
  "query": "ForgeAgent 是什么？",
  "count": 3,
  "results": [
    {
      "content": "ForgeAgent 是一个...",
      "source": "README.md",
      "score": 0.85,
      "source_type": "vector"
    }
  ]
}
```

### rag_ingest

将文档摄入知识库：

```json
{
  "tool": "rag_ingest",
  "args": {
    "content": "文档内容...",
    "source": "API 文档",
    "metadata_json": "{\"category\": \"技术文档\", \"version\": \"1.0\"}",
    "chunk_size": 500,
    "chunk_overlap": 50
  }
}
```

返回：

```json
{
  "ok": true,
  "source": "API 文档",
  "chunks": 12,
  "message": "成功摄入文档，生成了 12 个文本块"
}
```

## LCEL RAG Chain

```python
from app.modules.memory.rag import get_rag_chain, RagKnowledgeBase

# 构建 Chain
chain = get_rag_chain(
    rag=rag_knowledge_base,
    llm=chat_model,
    system_prompt="基于以下上下文回答用户问题：\n\n{context}"
)

# 执行
result = await chain.ainvoke({"question": "如何配置 RAG？"})
```

## 配置参数

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `RAG_ENABLED` | True | 是否启用 RAG |
| `RAG_PERSIST_DIRECTORY` | None | 向量存储路径 |
| `RAG_CHUNK_SIZE` | 500 | 分块大小 |
| `RAG_CHUNK_OVERLAP` | 50 | 分块重叠 |
| `RAG_EMBEDDING_MODEL` | None | 嵌入模型 |
| `RAG_EMBEDDING_API_KEY` | None | OpenAI API Key |
| `RAG_EMBEDDING_BASE_URL` | None | Embedding API 地址 |
| `RAG_RERANKER_MODEL` | None | Reranker 模型 |
| `RAG_VECTOR_WEIGHT` | 0.5 | 向量权重 |
| `RAG_BM25_WEIGHT` | 0.5 | BM25 权重 |
| `RAG_DEFAULT_TOP_K` | 5 | 默认返回数量 |
