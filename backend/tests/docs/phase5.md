# 阶段5 测试说明（SSE 任务事件流）

## 1. 测试如何归类

```text
backend/tests/
└── phase5/
    ├── conftest.py   # autouse 清表 + TestClient
    └── test_sse.py
```

## 2. 实现要点（摘要）

| 能力 | 说明 |
|------|------|
| **路径** | `GET /api/v1/tasks/{task_id}/events/stream` |
| **媒体类型** | `text/event-stream` |
| **帧格式** | `id` / `event`（与 `kind` 一致）/ `data`（JSON，结构与 GET `/events` 单条一致） |
| **增量** | `after_seq`、`last_event_id`、`Last-Event-ID`：仅 `seq` 更大的已提交行 |
| **结束** | 任务终态后若干轮无新事件则关闭流 |
| **错误** | 未知 `task_id` → **404**（在挂流前校验） |

## 3. 用例与断言要点

| 用例 | 断言要点 |
|------|----------|
| `test_sse_unknown_task_returns_404` | 非法 task_id → 404 |
| `test_sse_streams_events_until_task_done` | 200、`Content-Type`、首条 `plan_created`、含 `step_start`、与 REST 事件列表逐条一致 |
| `test_sse_after_seq_emits_only_newer` | `after_seq=首条 seq` 时，解析出的数据均 `seq` 更大 |

## 4. 如何运行

在 `backend/` 目录（Git Bash）：

```bash
source .venv/Scripts/activate
pytest tests/phase5 -q
pytest tests/phase2 tests/phase4 tests/phase5 -q
```

## 5. 文档与最佳实践

- 轮询式 SSE 与续传：`best_practice/forgeagent-sse-fastapi-phase5.md`
