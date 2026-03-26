# FastAPI 阶段2：分层 REST + 异步 Mock 后台任务（伪代码）

## 路由与分层

```text
api/v1/*.py          → 仅 HTTP：Query/Body 校验、Deps 注入 AsyncSession
services/*.py        → 用例编排；跨请求写库用独立 AsyncSessionLocal + begin()
repositories/*.py    → SQLAlchemy 查询/命令，无业务分支
schemas/*.py         → Pydantic v2 与 docs/API.md 对齐
```

## 创建任务后异步 Mock（避免与请求级 session 生命周期竞态）

```text
async def create_task(...):
  async with AsyncSessionLocal() as db:
    async with db.begin():
      # insert message + task，commit
      pass
  asyncio.create_task(run_mock_agent(task_id))

async def run_mock_agent(task_id):
  async with AsyncSessionLocal() as db:
    async with db.begin():
      append_event(...)
      task.status = success
```

要点：**提交后再** `create_task`；后台协程 **新开 session**，勿持有请求 `Depends(get_db)` 的会话。

## 统一错误体

```text
raise HTTPException(status_code=404, detail={"detail": "...", "code": "NOT_FOUND"})
# 或使用项目内 AppHTTPException 包装相同 shape
```

## OpenAPI

启动后访问 `/docs`；导出 JSON：`GET /openapi.json`。
