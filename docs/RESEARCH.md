# docs/RESEARCH.md

## 一、需求理解

**ForgeAgent** 定位为面向 **AI 应用开发者** 与 **Agent 使用者** 的 **AI 应用**：在 **MVP 范围**内提供 Agent 的 **四大核心能力**——**规划、记忆、工具使用、执行**；整体 **模块化、可重构**；并 **可选接入** 新技术（如 **MCP**、**Skills**、**认知框架**、**多 Agent** 等），目标是 **敏捷开发、可快速迭代** 的 Agent 框架/产品。

理解要点：

- **核心价值**：不是一次性脚本，而是可复用的「骨架」，让团队少造轮子、快试想法。
- **差异化意图**：通过模块化与可插拔扩展，在「够用」与「能演进」之间平衡，而非一上来对标 LangGraph 全量能力。
- **隐含约束**：MVP 需明确边界，否则易与成熟开源框架功能重叠、维护成本失控。

---

## 二、竞品分析

下表列出 **12** 个与「规划 / 记忆 / 工具 / 执行」及多 Agent、MCP 等相关的市面产品与开源框架（含云托管与编程范式差异），便于对照 ForgeAgent 的定位。

| 名称 | 类型 | 优点 | 缺点 |
|------|------|------|------|
| **LangGraph**（LangChain 生态） | 开源编排 / 状态图运行时 | 图结构显式建模状态与分支；人机协同、持久状态、流式与并行；与 LangChain 1.x 协同，生产案例多 | 学习曲线陡；概念多（节点/边/检查点）；重度依赖生态版本与最佳实践 |
| **LangChain** | 开源应用层 / Agent API | 上手快、文档与社区大；高层 Agent API 可建立在 LangGraph 上 | 抽象层厚，大项目易出现「拼接感」；需刻意做模块边界与测试 |
| **CrewAI** | 开源多 Agent（Python） | 角色化 Agent、Flow/Crew 分工清晰；内置大量工具与记忆叙事；社区活跃 | 与业务深度定制时可能需绕过约定；企业功能与开源边界需分清 |
| **Microsoft AutoGen** | 开源多 Agent | 多智能体协作、事件驱动与可扩展运行时方向明确；与 SK 整合路线清晰 | 0.4 大改版后 API 迁移成本；偏研究/实验与生产需额外工程化 |
| **Semantic Kernel** | 开源 SDK（.NET / Python 等） | 企业场景、插件与流程编排成熟；与 Azure/企业栈结合紧 | 心智模型偏「企业集成」；与纯 Python 极客向框架风格不同 |
| **Haystack** | 开源 Agent + 管道（Python） | 检索与 Agent 结合自然；组件边界清晰（Generator / Tool / Agent） | 强检索/RAG 场景更「主场」；通用 Agent 产品化需自补运营侧能力 |
| **LlamaIndex** | 开源数据 Agent / 工作流 | 「数据上的 Agent」叙事强；工作流、记忆与连接器生态全 | 概念多、版本迭代快；小团队易被功能面拖着走 |
| **OpenAI Agents SDK** | 开源 SDK（Python / JS） | 官方与模型/工具链协同；handoff、护栏、Tracing、MCP 等开箱 | 深度绑定 OpenAI 生态习惯；非 OpenAI 模型需适配心智 |
| **Pydantic AI** | 开源 Agent（Python） | 类型安全、模型无关、MCP / 人机确认等现代特性；与 Pydantic 生态一致 | 相对年轻；大型多团队规范需自建更多治理层 |
| **Google ADK**（`google/adk-python`） | 开源 Agent 工具包 | 工具与 MCP、多 Agent、部署故事完整；Gemini/Vertex 路径清晰 | 云与 Google 栈色彩强；跨云中立叙事需自行把握 |
| **Agno** | 开源 Agent / 运行时 | 强调轻量、模块化与性能；上手代码量少 | 生态与第三方教程体量小于头部框架；长期演进需观察 |
| **Amazon Bedrock Agents** | 云托管 Agent 服务 | 免运维、与 AWS 数据与知识库集成；企业治理与版本别名 | 供应商锁定；本地/离线/多云策略受限；调试体验依赖云控制台 |
| **DSPy** | 开源编程式 LLM 框架 | 模块化、可优化（编译/提示优化）；适合「程序即系统」的团队 | 主战场是声明式程序与优化，不是传统「Agent 产品壳」；Agent 需组合 ReAct 等模块 |

---

## 三、需求评估

**总体判断：方向合理，但「自研框架」与「MVP」之间存在结构性张力，需要把边界写死，否则容易踩坑。**

**合理之处：**

- **四大模块**（规划、记忆、工具、执行）与业界抽象高度同构，说明问题域清晰，便于对照成熟方案做裁剪。
- **模块化 + 可选 MCP / Skills / 多 Agent** 符合 2024–2025 的主流演进（MCP 已成互操作事实标准之一），技术选型不偏门。
- **目标用户是开发者** 时，类型安全、可测试、可观测比「万能 UI」更重要，与 Pydantic AI、LangGraph 等方向一致。

**明显坑点（建议直接正视）：**

1. **重复造轮子风险**  
   LangGraph、CrewAI、Pydantic AI、OpenAI Agents SDK、ADK 等已覆盖大部分组合。若 ForgeAgent 从零实现全套运行时，**长期维护成本**可能高于「薄封装 + 清晰领域层」。

2. **「认知框架」一词过大**  
   若指完整认知架构（目标、信念、反思、心理理论等），MVP 极易膨胀。更稳妥的是：**先落地可观测的 planning loop + 显式状态**，认知理论以**接口或可选插件**形式出现。

3. **多 Agent 与单 Agent 的复杂度不同量级**  
   多 Agent 需要 **消息路由、冲突解决、评测与追踪**；若 MVP 同时承诺多 Agent，迭代速度会明显下降。建议 **第一阶段单 Agent 闭环**，多 Agent 以 **编排适配层** 预留。

4. **记忆若不做数据与合规设计会返工**  
   长期记忆涉及 **持久化、权限、删除/遗忘、多租户**；MVP 可只支持 **会话级 + 可选向量存储接口**，避免早期绑定过重。

5. **Skills / MCP 并存时的「唯一真相」**  
   Skills（技能包约定）与 MCP（工具协议）解决不同层问题；若两者都一等公民，需 **统一「工具注册与权限」模型**，否则开发者会困惑。

**结论：** 需求在「开发者向 Agent 骨架」层面 **合理**；风险主要在 **范围与差异化表述**，而非单点技术不可行。

---

## 四、优化建议

1. **用一句话钉死 MVP**：例如「单 Agent + 显式规划循环 + 会话记忆 + 工具/MCP 注册表 + 可观测执行」，其余一律 **插件或后续里程碑**。  
2. **优先对接 MCP**：减少自研工具协议面；Skills 可作为「预置 MCP 打包」或「约定目录」而非第二套运行时。  
3. **执行层采用成熟抽象**：状态机或图（即便自研也建议 **对齐 LangGraph 级概念** 便于迁移），避免隐式全局状态。  
4. **评测与回放内置**：开发者框架若无最小 eval / trace，很难「快速迭代」；可对接 OpenTelemetry 或简单事件日志。  
5. **差异化放在「你的场景」而非「四大模块」**：四大模块是标配；差异化应来自 **ForgeAgent 解决的垂直工作流、模板或与你其他产品的集成**。  
6. **文档写清「不做什么」**：例如不做通用多租户 SaaS、不做重 UI 编排器（除非列为单独产品），降低用户错误预期。

---

## 五、参考资料

以下为本次调研中使用的公开文档与仓库入口（检索日期以各站点为准），便于复核与深入阅读。

| # | 说明 | 链接 |
|---|------|------|
| 1 | LangGraph 官方介绍 | https://www.langchain.com/langgraph/ |
| 2 | LangChain / LangGraph 1.0 博客 | https://blog.langchain.com/langchain-langgraph-1dot0/ |
| 3 | CrewAI 开源与文档 | https://github.com/crewAIInc/crewAI · https://docs.crewai.com/en/introduction |
| 4 | Microsoft：AutoGen 与 Semantic Kernel 协同 | https://devblogs.microsoft.com/semantic-kernel/microsofts-agentic-ai-frameworks-autogen-and-semantic-kernel/ |
| 5 | Haystack Agents 文档 | https://docs.haystack.deepset.ai/docs/agents |
| 6 | LlamaIndex 文档 | https://docs.llamaindex.ai/ |
| 7 | OpenAI Agents SDK（Python 文档） | https://openai.github.io/openai-agents-python |
| 8 | OpenAI Agents SDK GitHub | https://github.com/openai/openai-agents-python |
| 9 | Swarm（实验性，官方建议迁移到 Agents SDK） | https://github.com/openai/swarm |
| 10 | Pydantic AI 文档 / GitHub | https://ai.pydantic.dev/ · https://github.com/pydantic/pydantic-ai |
| 11 | Google ADK 文档 / Python 仓库 | https://google.github.io/adk-docs/ · https://github.com/google/adk-python |
| 12 | Agno 文档 | https://docs.agno.com/ |
| 13 | Amazon Bedrock Agents 概述 | https://aws.amazon.com/bedrock/agents/ |
| 14 | AWS：Agentic AI 框架与 Bedrock AgentCore 指引 | https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/bedrock-agents.html |
| 15 | DSPy 官网 / GitHub | https://www.dspy.ai/ · https://github.com/stanfordnlp/dspy |

---

*本文件由调研提示词 `M-prompts/M1research.md` 驱动生成，用于 ForgeAgent 需求验证与竞品对照。*
