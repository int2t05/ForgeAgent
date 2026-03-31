# ForgeAgent

面向开发与使用场景的 **AI Agent 应用**（非通用编排框架）：**规划、记忆、工具、执行** 四类能力，**Plan-and-Execute** 主循环；前端用于任务与可观测事件监控。MVP 能力与数据模型见 [`docs/architecture/TECH_DESIGN.md`](docs/architecture/TECH_DESIGN.md)；**完整文档索引**见 [`docs/README.md`](docs/README.md)。

## 仓库说明

本仓库为 **monorepo**：`frontend/`（Node/React）与 `backend/`（Python/FastAPI）**目录分离**。

- **Node / npm 仅在 `frontend/`**：仓库根目录**没有** `package.json`，避免与 Python 后端混在一起、也避免误用 npm workspace 在根目录产生多余 `node_modules`。
- **Python 仅在 `backend/`**：建议使用虚拟环境（`.venv`）与 `pip install -e .`，详见 [`START.md`](START.md)。

## 快速开始

详细安装、环境变量与启动命令见 **[`START.md`](START.md)**（前后端分步说明）。

摘要：

```bash
# 前端（在 frontend 目录）
cd frontend
npm install
npm run dev
```

```bash
# 后端（在 backend 目录，需先创建并激活 venv）
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

从仓库根目录复制环境变量模板：`copy .env.example .env`（Windows）或 `cp .env.example .env`（Unix），再按需填写；**勿将含真实密钥的 `.env` 提交到 Git**。

## 文档索引

详见 **[`docs/README.md`](docs/README.md)**。摘要：

| 文档 | 说明 |
|------|------|
| [`START.md`](START.md) | 脚手架安装、启动步骤、`frontend/package.json` 脚本说明 |
| [`AGENTS.md`](AGENTS.md) | AI 协作与工程规范（Cursor 等工具） |
| [`docs/architecture/TECH_DESIGN.md`](docs/architecture/TECH_DESIGN.md) | 技术设计、数据模型与 API 方向 |
| [`docs/architecture/ARCH.md`](docs/architecture/ARCH.md) | 全栈目录与模块职责（与实现对齐） |
| [`docs/conversation-flow.md`](docs/conversation-flow.md) | 对话、SSE、流式等业务流程 |
| [`docs/backend/TODO.md`](docs/backend/TODO.md) | 后端迭代 TODO |
| [`docs/backend/业务流程文档.md`](docs/backend/业务流程文档.md) | 业务流程与伪代码 |

接口字段与路径以运行后端 **`/openapi.json`** 为准（`TECH_DESIGN.md` 第 4 节为概要表）。

## 许可

见仓库根目录 [`LICENSE`](LICENSE)。
