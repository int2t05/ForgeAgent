# 阶段2 测试说明（HTTP API 非流式）

## 1. 测试如何归类

阶段2 与阶段0/1 **同级**，固定放在：

```text
backend/tests/
├── conftest.py          # 见下文：只负责尽早设置 DATABASE_URL，不做 autouse
├── test_runtime.sqlite  # 运行中生成（*.sqlite 已 gitignore），阶段0/2 共用 app.database 时连此文件
└── phase2/
    ├── conftest.py      # autouse 清表 + TestClient
    └── test_rest_api.py # REST + Mock 闭环用例
```

**根目录 `tests/conftest.py` 与 `tests/phase2/conftest.py` 如何分工？**

1. **根 conftest**：在模块 import 时设置 `DATABASE_URL` → `tests/test_runtime.sqlite`。这样无论先跑阶段0 还是阶段2，**首次**加载 `app.database` 时都会指向测试库，而不会误连开发库 `./data/forgeagent.db`。
2. **phase2 conftest**：只对 `tests/phase2/` 下用例生效，提供 **`autouse` 的 `drop_all`/`create_all`** 与 **`client` fixture**；不负责改环境变量，避免与阶段1 内存库逻辑交叉。

**阶段1** 仍使用 `tests/phase1/conftest.py` 的 **内存 SQLite + 独立 engine**，不读上述 `DATABASE_URL`。

## 2. 测试是怎么做的（方法概述）

| 手段 | 说明 |
|------|------|
| **Starlette `TestClient`** | 同步客户端，请求走完整 ASGI（含 `lifespan` → `init_db`），逼近真实 HTTP。 |
| **`DATABASE_URL` 指向专用文件** | 根 conftest 固定为 `tests/test_runtime.sqlite`，与开发库分离。 |
| **每用例 `drop_all` + `create_all`** | 仅 `tests/phase2/conftest.py` 的 `autouse`，只影响阶段2 用例隔离。 |
| **Mock Agent** | `POST /tasks` 后服务端 `asyncio.create_task` 写事件并置 `success`；用例中用 **短轮询** 等待终态（最多约 3s），避免 `sleep` 固定过长。 |
| **`@pytest.mark.phase2`** | 与 `pyproject.toml` 中 marker 登记一致，支持 `pytest -m phase2` 只跑本阶段。 |

**不在阶段2测的内容**：SSE 流式行为与顺序（见 `tests/phase5/`）。

## 3. 覆盖的 API 与文档依据

- 里程碑：`docs/DEVELOP_ORDER.md` 阶段2（REST 非流式）。
- 契约：`docs/API.md` 中会话、任务、事件 GET、设置、工具列表；健康检查单独 `GET /health`。

## 4. 用例与断言要点

| 用例 | 断言要点 |
|------|----------|
| `test_health` | `GET /health` → 200 与 `{status: ok}` |
| `test_sessions_messages_tasks_flow` | 会话 → 任务 → Mock 终态 `success` → `plan.steps` → `task_events` 升序与 `after_seq` |
| `test_task_unknown_session` | 不存在 `session_id` → 404，`code=NOT_FOUND` |
| `test_settings_roundtrip_and_rejects_secret_key` | PUT/GET 一致；body 含 `api_key` 键名 → 400，`SECRET_FIELD` |
| `test_tools_list` | `GET /api/v1/tools` 含 `builtin` |

## 5. 如何运行

在 `backend/` 目录：

```bash
source .venv/Scripts/activate   # Windows Git Bash
pytest tests/phase2 -q          # 推荐：按目录跑阶段2
pytest -m phase2 -q             # 可选：按 marker 跑（若其它目录也挂了 phase2 会一并执行）
```

## 6. 排障提示

- **ImportError / 数据库被锁**：确保没有其它进程长时间占用 `test_runtime.sqlite`；可删除该文件后重跑。
- **Mock 未在超时内 success**：检查本机事件循环与负载；可适当增大 `test_rest_api.py` 中轮询 `deadline`（当前 3s）。
