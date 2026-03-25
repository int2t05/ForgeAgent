# FastAPI 骨架与 uvicorn 入口（阶段 0）

## 场景

单模块 FastAPI 应用，通过 **可编辑安装** 用包路径启动，避免 `PYTHONPATH` 手搓与文档口径不一致。

## 要点（伪代码）

```text
# pyproject.toml：[tool.hatch.build.targets.wheel] packages = ["app"]
# 目录：backend/app/main.py 中 app = FastAPI(...)  # 模块内 ASGI 实例名也叫 app

# 在 backend/ 下
python -m venv .venv
# Git Bash: source .venv/Scripts/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e .

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 含义：包 app → 模块 main → 变量 app（FastAPI 实例）
# GET /health -> {"status": "ok"}
```

## 易错点

- `uvicorn app.main:app` 中：**第一个** `app` 是 **Python 包名**（目录 `backend/app/`），**第二个** `app` 是 **`main.py` 里的 FastAPI 实例**；二者同名很常见，但职责不同。
- Hatch 的 `packages` 必须与磁盘上的包目录名一致，否则 `pip install -e .` 后 import 失败。
