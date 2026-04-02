# ForgeAgent 初始化与启动

本文档说明仓库脚手架的**安装命令**、**`frontend/package.json` 脚本摘要**，以及如何**分别启动**前端与后端。人类入口总览见 [`README.md`](README.md)；架构与数据模型见 [`docs/README.md`](docs/README.md)。

---

## 1. 初始化命令

前后端**解耦**：Node 依赖**只**装在 `frontend/`，仓库根目录不再有 `package.json`。若你曾用过根目录 `npm install`（旧版 workspace），根目录可能仍留有 `node_modules`：关闭占用该目录的进程后**整目录删除**即可，以后只在 `frontend` 下执行 `npm install`。

前端（在 `frontend` 目录，仅需一次，或依赖变更后重跑）：

```bash
cd frontend
npm install
```

后端（建议在 `backend` 下使用虚拟环境，避免污染全局 Python）：

```bash
cd backend
python -m venv .venv
```

Windows（PowerShell）：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
```

macOS / Linux：

```bash
source .venv/bin/activate
pip install -e .
```

可选：从仓库根目录复制环境变量模板后再按需填写（勿提交含密钥的 `.env`）：

```bash
copy .env.example .env
```

模板中与 Agent 相关的项包括：`DATABASE_URL`、`LANGGRAPH_CHECKPOINT_SQLITE_PATH`（与业务库分离的检查点 SQLite）、`SESSION_MEMORY_MAX_MESSAGES`、`SESSION_BLACKBOARD_MAX_NOTES`、`LLM_CONTEXT_WINDOW_TOKENS` 等，说明见根目录 [`.env.example`](.env.example) 与 [`backend/app/core/config.py`](backend/app/core/config.py)。

---

## 2. `package.json`

仓库根目录**无** `package.json`。前端独立见 `frontend/package.json`（依赖与脚本以该文件为准）。

- **脚本**：`dev`（Vite）、`build`、`lint`、`format`、`format:check`、`preview`
- **运行时**：`react`、`react-dom`
- **开发**：`vite`、`typescript`、`tailwindcss`、`@tailwindcss/vite`、`eslint`、`typescript-eslint`、`prettier`、`eslint-config-prettier` 等

完整内容见仓库中的 `frontend/package.json`。

---

## 3. 启动项目步骤

### 前端（`npm install` + `npm run dev`）

在 **`frontend` 目录**：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开终端提示的本地地址（默认 `http://localhost:5173/`）。

### 后端（FastAPI 健康检查）

在已激活虚拟环境且已 `pip install -e .` 的前提下，于 `backend` 目录：

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Git Bash（已激活 `.venv`）同上，工作目录与模块路径与 [`README.md`](README.md) 一致：

```bash
source .venv/Scripts/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/health` 应返回 `{"status":"ok"}`；OpenAPI 文档：`http://127.0.0.1:8000/docs`。

### 常用质量命令（前端）

在 `frontend` 目录：

```bash
npm run lint
npm run format
npm run build
```

---

## 4. 目录约定（与 `AGENTS.md` / `docs/architecture/TECH_DESIGN.md` 一致）

- `frontend/`：React + Vite + TypeScript + Tailwind + ESLint + Prettier；**所有** `npm` 命令在此目录执行
- `backend/`：Python 3.11+、FastAPI、可编辑安装 `pip install -e .`
- `docs/`：主题分目录（`architecture/`、`backend/` 等），索引见 [`docs/README.md`](docs/README.md)
- 仓库根目录：`README.md`、`AGENTS.md`、`.env.example`、**无** `package.json`
