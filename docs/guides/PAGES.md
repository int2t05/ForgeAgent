# ForgeAgent 前端页面设计（MVP）

本文档将 [`PRD.md`](PRD.md) §4 页面结构落实为 **路由、区块与数据依赖**；API 契约见 [`API.md`](API.md)。**不包含组件/代码实现。**

---

## 1. 路由与信息架构

| 路由 | 页面角色 | PRD 对应 |
|------|----------|----------|
| `/` | 首页 / 仪表盘 | 最近任务、快捷发起任务入口 |
| `/tasks` | 任务列表 | 全部任务：状态、时间、摘要 |
| `/tasks/:taskId` | 任务详情（监控核心） | 计划、执行时间线、错误与重规划、可选原始日志 |
| `/settings` | 设置（最小） | MCP/Skills 非密钥配置、密钥说明 |
| `/about` | 关于 / 帮助 | MVP 边界、Skills 说明 |

**默认会话策略（建议）**：首次进入应用时若无 `session_id`，可自动调用 **创建会话**（[`API.md`](API.md) §3），将 `session_id` 存于内存或 `sessionStorage`，首页与发起任务共用；用户清空站点数据后重新创建。**不**在 MVP 强制做多用户会话隔离 UI。

---

## 2. 分页面说明

### 2.1 首页 `/`

| 项目 | 说明 |
|------|------|
| 主要区块 | ① 标题与简短产品说明；② **最近任务**（条数如 5～10，展示状态、摘要、`updated_at`）；③ **发起任务**：多行文本输入 + 提交按钮。 |
| 调用的 API | `GET /api/v1/tasks`（`limit` 小、`offset` 0，可选按更新时间排序）；`POST /api/v1/tasks`（提交时：`session_id` + `user_message`）。 |
| 提交后导航 | 成功返回 `task_id` 后跳转 **`/tasks/:taskId`**，满足 PRD「进入任务 → 看步骤 → 看结果」路径。 |
| 辅助链接 | 导航至「全部任务」「设置」「关于」。 |

### 2.2 任务列表 `/tasks`

| 项目 | 说明 |
|------|------|
| 主要区块 | ① 筛选（可选）：按 `status`；② 表格或卡片列表：`status`、`summary`、`created_at`/`updated_at`；③ 行点击进入详情。 |
| 调用的 API | `GET /api/v1/tasks`（分页 `limit`/`offset`；可选 `status`）。 |
| 实时 | 列表页可用 **`refetchInterval`** 或对进行中的任务短轮询；非必须 SSE。 |

### 2.3 任务详情 `/tasks/:taskId`

| 项目 | 说明 |
|------|------|
| 主要区块 | ① **顶栏**：任务状态、`plan_version`、返回列表；② **计划区**：步骤列表（与 `GET /api/v1/tasks/{id}` 中 `plan` 一致）；③ **执行时间线**：按 `seq` 展示 `task_events`（模块标签、kind、耗时若 payload 含）；④ **错误区**：`error_message` 与 `kind=error` 事件高亮；⑤ **重规划记录**：`kind=replan` 折叠列表或融入时间线；⑥ **原始日志（可选）**：大块 `payload` 折叠，等宽字体。 |
| 调用的 API | 首屏：`GET /api/v1/tasks/{task_id}`、`GET /api/v1/tasks/{task_id}/events`（可从 `after_seq=0` 或省略换全量第一页）；**实时**：`GET /api/v1/tasks/{task_id}/events/stream`（SSE）。 |
| 实时策略 | **主路径 SSE**；断线后先用 `GET .../events?after_seq=<最后 seq>` **补拉**，再重连 SSE（与 [`TECH_DESIGN.md`](TECH_DESIGN.md) 一致）。 |
| TanStack Query | `task` 详情 query；`events` 初始 query + SSE 增量合并或 invalidate；注意 `seq` 单调避免乱序覆盖。 |

### 2.4 设置 `/settings`

| 项目 | 说明 |
|------|------|
| 主要区块 | ① MCP 连接**元数据**（名称、URL、是否启用等，**无密钥输入框**）；② Skills 路径或启用开关；③ 静态说明：LLM/MCP 密钥仅通过服务端环境变量配置，勿写入仓库与前端。 |
| 调用的 API | `GET /api/v1/settings`、`PUT /api/v1/settings`。 |
| 保存反馈 | 成功/失败 toast 或行内提示；不阻塞导航。 |

### 2.5 关于 `/about`

| 项目 | 说明 |
|------|------|
| 主要区块 | 静态 Markdown 渲染或硬编码文案：**单 Agent**、**会话级记忆**、**Skills 与工具注册表关系**、指向 `PRD`/`TECH_DESIGN` 的链接（可选）。 |
| 调用的 API | 无必须请求；可选 `GET /health` 显示后端连通（开发友好）。 |

---

## 3. 全局布局与导航

- **顶栏或侧栏**：产品名、链接 `首页`、`任务`、`设置`、`关于`。
- **加载与错误**：列表/详情骨架屏；详情页 SSE 失败时提示用户并依赖 REST 刷新。

---

## 4. 交互与视觉（与 PRD §5 对齐）

| 项目 | 要求 |
|------|------|
| 风格 | 简洁现代；中文；**日志/JSON 使用等宽字体**。 |
| 色彩 | 中性背景 + **单一强调色**区分进行中 / 成功 / 失败；避免多色块干扰排障。 |
| 交互 | 时间线条目可 **展开/折叠**；工具返回等长内容 **默认摘要 + 展开全文**；关键操作（若 MVP 提供「重新执行」类按钮）需 **二次确认** 或明确后果文案。 |
| 响应式 | 1920×1080 与常见笔记本宽度布局无严重错位。 |

---

## 5. 页面与数据流总览（实现参考）

| 页面 | 主要 Query / Mutation | SSE |
|------|------------------------|-----|
| `/` | `GET /tasks`（节选）、`POST /tasks` | 否 |
| `/tasks` | `GET /tasks` | 可选轻量轮询 |
| `/tasks/:taskId` | `GET /tasks/:id`、`GET /tasks/:id/events` | `GET .../events/stream` |
| `/settings` | `GET /settings`、`PUT /settings` | 否 |
| `/about` | 无必须 | 否 |

---

*文档版本：MVP；拖拽式工作流画布、多租户控制台不在范围内。*
