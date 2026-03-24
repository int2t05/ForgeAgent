# ForgeAgent AI 开发指令

本文档供 Cursor 等 AI 编程工具在 **ForgeAgent** 仓库内协作时使用。规范分 **必须** 与 **建议**；冲突时以 `docs/PRD.md`、`docs/TECH_DESIGN.md` 为准。

---

## 项目概述

**ForgeAgent** 是一款 **AI Agent 应用**（非通用编排框架）：在单一产品内提供 **规划、记忆、工具、执行** 四类能力，采用 **Plan-and-Execute** 主循环；支持 **MCP**、**Skills 约定**（与统一工具注册表对齐）；前端用于监控任务执行与可观测事件。

**MVP 边界（必须遵守）**：单 Agent + 显式规划循环 + 会话级记忆 + 工具/MCP 注册表 + 可观测执行。多 Agent 生产编排、完整多租户 SaaS、拖拽式复杂工作流画布、MVP 内完整长期记忆治理等 **不做**。

**技术栈（建议与实现对齐）**：

- 前端：React、TypeScript、Vite、Tailwind CSS（具体版本以 `frontend/package.json` 为准）；React Router；TanStack Query + 轻量全局状态（如 Zustand）。
- 后端：Python 3.11+、FastAPI；Agent 运行时以 LangGraph + LangChain 为主。
- 数据库：SQLite + SQLAlchemy 2.0 async（MVP）。
- API：REST 为主；单任务执行过程可用 **SSE**（`text/event-stream`）推送事件。

---

## 开发规范

永远参考最新文档的最佳实践开发

依赖包版本要确定好(尽量最新且不冲突)

### 代码与类型


| 层级  | 必须                                                                                     | 建议                                |
| --- | -------------------------------------------------------------------------------------- | --------------------------------- |
| 前端  | TypeScript **严格模式**（`strict: true`）；禁止为图省事滥用 `any`；公共类型与 API 响应类型对齐 OpenAPI 或共享 schema | 优先函数式组件；复杂副作用用自定义 Hook 收敛         |
| 后端  | 公开 API 有类型与 Pydantic 模型；异步路由与 DB 访问方式一致（勿混用阻塞调用拖死事件循环）                                 | 业务逻辑与 HTTP 层分层，便于单测               |
| 通用  | **密钥、API Key、MCP 密钥不得进入前端打包产物与公开仓库**；仅环境变量或服务端注入；日志中对敏感字段脱敏                            | 新模块注明与 PRD「四模块」的对应关系（规划/记忆/工具/执行） |


### 组件与 UI


| 项目    | 必须                                                | 建议                                       |
| ----- | ------------------------------------------------- | ---------------------------------------- |
| React | 可复用 UI 与页面容器分离；列表/详情/时间线职责清晰                      | 监控类页面避免过度全局状态                            |
| 样式    | 使用 **Tailwind CSS** Utility；禁止内联大段任意 CSS 堆叠导致不可维护 | 状态色与 PRD 一致：中性背景 + **单一强调色** 表达进行中/成功/失败 |


### 命名约定


| 类别           | 必须                             | 示例                                    |
| ------------ | ------------------------------ | ------------------------------------- |
| 前端组件         | PascalCase                     | `TaskTimeline.tsx`                    |
| 前端文件（非组件）    | camelCase 或 kebab-case，与现有目录一致 | `useTaskEvents.ts`                    |
| Python 模块/函数 | PEP 8：`snake_case`             | `task_service.py`、`get_task_by_id`    |
| 数据库表/列       | `snake_case`（见 TECH_DESIGN）    | `task_events`、`plan_version`          |
| API 路径       | 小写、资源名词、复数集合                   | `/api/tasks`、`/api/tasks/{id}/events` |


---

## 目录结构

**当前仓库**为 **monorepo**（与技术设计一致）：产品与架构文档在 `docs/`，实现代码在 `frontend/` 与 `backend/`。

```
ForgeAgent/
├── README.md                 # 人类入口：快速开始与文档索引
├── START.md                  # 安装与启动命令（脚手架）
├── AGENTS.md                 # 本文件：AI 协作规范（勿随意删改核心约束）
├── .env.example              # 环境变量模板（勿提交含密钥的 .env）
├── .gitignore
├── frontend/                 # React + Vite + TS + Tailwind；npm 仅在此目录执行
├── backend/                  # FastAPI；Python 依赖见 pyproject.toml；Agent/SQLite 等随实现补充
├── docs/
│   ├── PRD.md
│   ├── RESEARCH.md
│   └── TECH_DESIGN.md
├── M-prompts/                # 文档/提示词模板（若保留）
└── LICENSE
```

**必须**：前后端分目录；**不得在仓库根目录**引入 `package.json` 或根级 npm workspace（Node 依赖仅存在于 `frontend/`，避免与后端工具链混淆）。避免前端依赖或误打包后端密钥。  
**建议**：共享类型若存在，用显式包或生成 OpenAPI 客户端，避免手写双份漂移。

---

## Git 提交规范

**必须** 使用 [Conventional Commits](https://www.conventionalcommits.org/) 风格，便于变更追溯：

- 格式：`<type>(<scope>): <description>`
- 常用 `type`：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`
- `scope` 可选：`frontend`、`backend`、`api`、`agent` 等
- 正文：说明「改了什么、为何」，必要时换行写 breaking change

**示例**：

- `feat(backend): add SSE endpoint for task events`
- `fix(frontend): debounce task list refetch on focus`

**建议**：一个提交只做一类意图；大功能拆多次可审的提交。

---

## AI 开发注意事项

### 红线（必须）

- **不得** 将 API Key、LLM 密钥、MCP 密钥写入前端代码、`.env` 示例以外的公开模板或提交记录中的明文。
- **不得** 在无用户明确要求时 **删除或弱化** `docs/PRD.md`、`docs/TECH_DESIGN.md` 中与 MVP 边界相关的约束表述。
- **不得** 为「省事」实现与 PRD 冲突的能力（例如 MVP 内做多 Agent 编排、通用多租户计费）并标为默认路径。
- **不得** 在未说明的情况下改写 `**AGENTS.md` 的核心约束**；若需调整规范，应显式说明变更原因并保持与 PRD 一致。

### 优先实现（建议顺序）

1. 后端：任务/会话/事件数据模型与持久化，与 TECH_DESIGN 字段一致。
2. Agent：Plan-and-Execute 最小闭环 + 统一工具注册表（含 MCP 或文档化 mock）。
3. API + SSE：按任务 ID 可拉取/推送可观测事件。
4. 前端：任务列表 → 任务详情（计划 + 时间线）→ 设置占位。

### 复杂功能处理

- **必须** 先对照 PRD 验收标准；超出 MVP 的放在 feature flag、`/docs` 后续章节或单独 ADR，而非默认主路径。  
- **建议** 对 LangGraph：从最小节点图开始，避免一上来全量多分支；重规划次数可配置上限。  
- **建议** 长日志、大 payload 采用分页、摘要默认、展开全文，避免一次渲染拖垮页面。

---

## 测试要求

### 如何验证（必须）

- **后端**：对核心服务层与 API 契约编写自动化测试（pytest 等）；任务状态迁移、事件顺序、`task_id + seq` 语义须有覆盖。  
- **契约**：前后端以 OpenAPI 或固定 fixture 对齐；变更 API 时同步示例与类型。

### 手动测试（建议必测场景）

- 端到端：单次任务从创建 → 计划可见 → 执行步骤 → 成功或失败状态与错误信息可见。  
- 安全：确认构建产物与仓库中无密钥；浏览器网络面板无敏感头泄露。  
- UI：PRD 所述路径「进入任务 → 看步骤 → 看结果」≤3 次主要点击；1920×1080 与常见笔记本宽度布局无严重错位。

---

## 界面风格


| 项目  | 必须                                            | 建议                                       |
| --- | --------------------------------------------- | ---------------------------------------- |
| 整体  | **简洁现代**；信息层级清晰；中文界面；日志/JSON 使用 **等宽字体**      | 减少装饰性组件，以可读性与排障效率为先                      |
| 色彩  | **中性背景** + **单一强调色** 区分进行中/成功/失败；避免多块高饱和色干扰排障 | 具体色值在实现后收敛到 Tailwind theme 或 CSS 变量，全站一致 |
| 交互  | 长内容默认摘要 + 展开全文；关键操作（如重新执行）有明确后果说明或二次确认        | 步骤时间线可展开/折叠                              |


---

*若本文件与 `docs/PRD.md` / `docs/TECH_DESIGN.md` 不一致，以两份文档为准并应更新本文件。*