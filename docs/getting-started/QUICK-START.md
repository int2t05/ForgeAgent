# 快速开始

## 1. 克隆项目

```bash
git clone <repo-url>
cd ForgeAgent
```

## 2. 环境变量

```bash
cp .env.example .env
# 编辑 .env 填写 API Key
```

## 3. 启动后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -e .

# 启动服务
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

## 5. 访问

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs
