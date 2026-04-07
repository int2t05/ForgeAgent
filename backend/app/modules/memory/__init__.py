"""记忆域模块：Learn 节点、LLM 上下文窗口管理、RAG 知识库。

核心组件：
  - learn.py：Learn 节点（反思、重规划判断、最终回答生成）
  - context.py：LLM 上下文窗口管理（消息加载、Token 计数、预算截断、对话摘要）
  - rag.py：RAG 知识库（文档分块、向量化、混合检索、Rerank 重排序）
  - rag_integration.py：RAG 与 Agent 工作流融合（自动检索注入 Planner 上下文）

使用方式（按需导入以避免循环依赖）：
  from app.modules.memory.learn import learn_node, route_after_learn
  from app.modules.memory.context import SessionLLMContextManager, estimate_messages_tokens, truncate_chat_messages_to_budget
  from app.modules.memory.rag import RagKnowledgeBase, get_rag_chain, SearchResult
  from app.modules.memory.rag_integration import build_rag_context_for_planner, retrieve_rag_context
"""
