# 安装配置详解

## 环境要求

- Node.js ≥ 18
- Python ≥ 3.11
- SQLite (默认)

## 前端配置

### 依赖安装

```bash
cd frontend
npm install
```

### 环境变量

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## 后端配置

### 虚拟环境

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
```

### 依赖安装

```bash
pip install -e .
```

### 环境变量 (.env)

| 变量 | 说明 | 必填 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | 是 |
| `OPENAI_MODEL` | 模型名称，默认 gpt-4 | 否 |
| `ANTHROPIC_API_KEY` | Anthropic API Key | 否 |
| `LANGGRAPH_CHECKPOINT_SQLITE_PATH` | checkpoint 存储路径 | 否 |

## 数据库

SQLite 数据库 `forgeagent.db` 会在首次启动时自动创建。
