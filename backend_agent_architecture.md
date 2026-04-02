# 后端 Agent 架构核心文件定位

## 目录结构总览

```
backend/app/
├── api/v1/              # API路由层
├── core/                # 核心配置
├── models/              # 数据模型
├── modules/             # 核心模块（Agent架构主体）
├── repositories/        # 数据访问层
├── schemas/             # Pydantic schemas
├── services/            # 业务服务层
└── shared/              # 共享工具
```

## Agent 架构核心文件

### 1. 执行引擎 (modules/execution/)
| 文件 | 功能 |
|------|------|
| `step_react_loop.py` | **ReAct 循环执行核心** - Agent的主循环 |
| `nodes.py` | 节点定义 |
| `tool_runner.py` | 工具运行器 |
| `llm_reply.py` | LLM回复处理 |
| `stream_split.py` | 流式输出分割 |

### 2. 工作流管理 (modules/workflow/)
| 文件 | 功能 |
|------|------|
| `graph.py` | 图结构定义 |
| `state.py` | 状态管理 |

### 3. 规划模块 (modules/planning/)
| 文件 | 功能 |
|------|------|
| `llm.py` | 规划用LLM接口 |
| `nodes.py` | 规划节点定义 |

### 4. 记忆系统 (modules/memory/)
| 文件 | 功能 |
|------|------|
| `session_blackboard.py` | 会话黑板（共享数据） |
| `session_context.py` | 会话上下文管理 |
| `checkpointer.py` | 状态检查点 |
| `learner_node.py` | 学习者节点 |

### 5. 工具系统 (modules/tools/)
| 文件 | 功能 |
|------|------|
| `registry.py` | 工具注册表 |
| `builtin.py` | 内置工具定义 |
| `builtin_executor.py` | 内置工具执行器 |
| `mcp_sources.py` | MCP工具源 |
| `skill_sources.py` | Skill工具源 |

### 6. 提示词管理 (modules/prompts/)
| 文件 | 功能 |
|------|------|
| `step_react.py` | ReAct模式提示词 |
| `step_react_verify.py` | ReAct验证提示词 |
| `planning.py` | 规划提示词 |
| `assistant_reply.py` | 助手回复提示词 |
| `learner_reflection.py` | 学习者反思提示词 |
| `catalog.py` | 提示词目录 |

### 7. 服务层 (services/)
| 文件 | 功能 |
|------|------|
| `session_service.py` | 会话服务 |
| `task_service.py` | 任务服务 |
| `tool_service.py` | 工具服务 |
| `event_stream_service.py` | 事件流服务 |

### 8. 核心LLM支持 (core/)
| 文件 | 功能 |
|------|------|
| `llm_openai.py` | OpenAI LLM接口 |
| `llm_retry.py` | LLM重试机制 |
| `llm_context_budget.py` | 上下文预算管理 |

### 9. API路由 (api/v1/)
| 文件 | 功能 |
|------|------|
| `sessions.py` | 会话API |
| `tasks.py` | 任务API |
| `tools.py` | 工具API |
| `settings.py` | 设置API |

## Agent 执行流程

```
API请求 (sessions.py/tasks.py)
    ↓
service层 (session_service/task_service)
    ↓
execution/step_react_loop.py (ReAct主循环)
    ├── planning/planning.py (规划下一步)
    ├── execution/nodes.py (执行节点)
    ├── tools/tool_runner.py (运行工具)
    └── memory/session_context.py (上下文管理)
    ↓
workflow/graph.py (状态图流转)
    ↓
LLM调用 (core/llm_openai.py)
```
