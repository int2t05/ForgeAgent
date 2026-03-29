# FastAPI + SSE（任务事件流）— ForgeAgent 阶段5 要点

## 目标

`GET /api/v1/tasks/{task_id}/events/stream` 返回 `Content-Type: text/event-stream`，`data` 字段与 `GET .../events` 单条 JSON 对齐（`seq/ts/module/kind/payload`）。

## 实现策略（MVP）

- **轮询已提交行**：节点内 `async with db.begin()` 提交后，SSE 侧用短间隔查询 `seq > last_sent`，避免未提交事务对其它会话不可见的问题。
- **结束条件**：`tasks.status in {success, failed, cancelled}` 且连续多轮查询无新事件则结束生成器，释放连接。
- **续传**：`Query after_seq` / `last_event_id` 与 `Last-Event-ID` 头（EventSource），语义均为「只推送 `seq` 更大」的行。

## 伪代码

```text
async def sse_gen(task_id, after_seq):
    last = after_seq
    stable = 0
    while True:
        rows = repo.list_events(task_id, seq > last, limit=200)
        task = repo.get_task(task_id)
        for row in rows:
            stable = 0
            yield sse_frame(id=row.seq, event=row.kind, data=to_json(row))
            last = row.seq
        if not rows and task.status in terminal:
            stable += 1
            if stable >= THRESHOLD: return
        sleep(SHORT_POLL)
```

## HTTP 头

- `Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`（经 Nginx 时减少缓冲）。

## 测试注意

- `TestClient.stream("GET", ...)` 同步读 `read(n)`，配合短轮询任务终态，避免单测在 Windows SQLite 上与后台 `create_task` 抢锁。
