# Pytest：阶段8 总验收（E2E + 契约巡检）

**场景**：MVP 收尾阶段需要 **真实 Agent 路径** 上的回归用例，与阶段2 的 Mock/分测互补。

## 要点（伪代码）

### 1. 每测隔离库（与阶段2 同款）

```text
fixture autouse _reset_db:
  await engine.dispose()
  async with engine.begin():
    drop_all(Base.metadata)
    create_all(Base.metadata)
  yield
```

- 避免并行用例或目录间 **残留行** 导致 `total`、`seq` 断言漂移。

### 2. 异步任务轮询

```text
def wait_success(client, task_id, timeout):
  until = now + timeout
  loop:
    body = GET /api/v1/tasks/{id}
    if body.status == "success": return
    sleep(short)
  fail "timeout"
```

- Agent 在后台 `asyncio` 中跑，HTTP 用例侧 **不能用** 单请求假定已终态；超时与步长按机器调参（本地可 10–15s 量级）。

### 3. `seq` 严格连续

```text
events = GET /api/v1/tasks/{id}/events → events[]
seqs = [e.seq for e in events]
assert seqs == [1, 2, ..., len(seqs)]
```

- 强于「仅递增」：暴露 **跳号** 或重复分配 `seq` 的 bug。

### 4. OpenAPI 冒烟

```text
paths = GET /openapi.json → paths
assert "/health" in paths
assert "/api/v1/tasks" in paths
# ... 业务关键前缀
```

- 路由重构或 `include_router` 遗漏时快速失败，不依赖手写路径表与实现双份维护（仍以 CI 为准）。

## 与前端阶段8

- 阶段6/7 以 **`npm run lint` + `npm run build`** 做壳与监控闭环的门禁；阶段8 后端用例 **不替代** 浏览器手工清单（见 `docs/DEVELOP_ORDER.md` §6）。
