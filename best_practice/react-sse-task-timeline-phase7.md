# React 任务时间线 + SSE（fetch ReadableStream）— ForgeAgent 阶段7

简洁伪代码，便于对照 `frontend/src/api/sse.ts` 与 `useTaskTimeline`。

## 为何不用 EventSource

- 后端每条 SSE 帧使用不同 `event: <kind>`；`EventSource` 需为每种 `kind` 注册监听，扩展成本高。
- `fetch` + `ReadableStream` 统一解析 `data:` JSON，与 `GET /events` 形状一致。

## 流程（与 API.md 断线补拉对齐）

```text
1. GET /tasks/{id}/events?limit=200 分页循环直到不足一页 → 本地 Map<seq, event>
2. GET /tasks/{id}/events/stream?after_seq=maxSeq → 增量帧，解析后 merge（seq 去重）
3. 流正常关闭后 → 再 GET /events?after_seq=lastSeq 补最后一轮缺口（可选双保险）
4. 关键 kind（plan_created / replan / error）→ invalidateQueries(['task', id])
5. 运行中任务 → useTaskDetail 设 refetchInterval 兜底刷新 plan/status
```

## SSE 缓冲解析（核心）

```text
buffer += decoder.decode(chunk, { stream: true })
repeat:
  split by "\n\n" → complete_blocks, rest
  for block in complete_blocks:
    lines where line.startsWith("data:")
    dataStr = join(data lines)
    event = JSON.parse(dataStr)  // 与 REST 单条一致
  buffer = rest
until stream done; then decoder.decode() flush 再 split 一次
```

## 注意

- 卸载组件时 `AbortController.abort()`，忽略 `AbortError`。
- 长 payload：列表默认摘要，详情行内「展开全文」满足 PRD 可读性。
