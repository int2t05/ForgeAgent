# ForgeAgent

面向开发与使用场景的 **AI Agent 应用**（非通用编排框架）：**规划、记忆、工具、执行** 四类能力，**Plan-and-Execute** 主循环；前端用于任务与可观测事件监控。MVP 边界与验收见 [`docs/PRD.md`](docs/PRD.md)。

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
uvicorn forgeagent_backend.main:app --reload --host 127.0.0.1 --port 8000
```

从仓库根目录复制环境变量模板：`copy .env.example .env`（Windows）或 `cp .env.example .env`（Unix），再按需填写；**勿将含真实密钥的 `.env` 提交到 Git**。

## 文档索引

| 文档 | 说明 |
|------|------|
| [`START.md`](START.md) | 脚手架安装、启动步骤、`frontend/package.json` 脚本说明 |
| [`AGENTS.md`](AGENTS.md) | AI 协作与工程规范（Cursor 等工具） |
| [`docs/PRD.md`](docs/PRD.md) | 产品需求与 MVP 边界 |
| [`docs/TECH_DESIGN.md`](docs/TECH_DESIGN.md) | 技术设计、数据模型与 API 方向 |
| [`docs/API.md`](docs/API.md) | REST/SSE 接口契约（MVP） |
| [`docs/PAGES.md`](docs/PAGES.md) | 前端路由与页面数据依赖（MVP） |
| [`docs/DEVELOP_ORDER.md`](docs/DEVELOP_ORDER.md) | 全栈开发顺序与里程碑（MVP） |
| [`docs/RESEARCH.md`](docs/RESEARCH.md) | 调研与竞品对照 |

## 许可

见仓库根目录 [`LICENSE`](LICENSE)。
