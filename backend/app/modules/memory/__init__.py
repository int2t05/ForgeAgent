"""记忆域：会话上下文管理、共享黑板、LLM 上下文预算与对话摘要。

核心能力：
  - 会话上下文（session_context.py）：消息列表转 LangChain 格式、历史装填
  - 共享黑板（session_blackboard.py）：跨步骤的键值存储、检查点同步
  - 上下文预算（llm_context_budget.py）：token 估算、超限截断、错误识别
  - 对话摘要（conversation_summary.py）：超长会话的 LLM 压缩
  - Observation 压缩（tool_observation_compact.py）：工具返回值裁剪以控制 prompt 长度
  - Token 计数（token_counter.py）：tiktoken 本地精确计数
  - 检查点（checkpointer.py）：LangGraph 状态持久化与清理
  - 学习者节点（learner_node.py）：执行后反思与经验沉淀

使用场景：
  - Planner 加载会话历史作为规划上下文
  - ReAct 循环组装消息列表时应用预算截断
  - Actor 完成后触发 Learner 反思

使用方式（按需导入以避免循环依赖）：
  from app.modules.memory.session_context import SessionLLMContextManager
  from app.modules.memory.llm_context_budget import estimate_messages_tokens
"""
