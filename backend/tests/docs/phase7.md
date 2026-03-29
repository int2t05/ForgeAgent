# 阶段7 测试说明（前端监控闭环）

对齐 [docs/DEVELOP_ORDER.md](../../docs/DEVELOP_ORDER.md) **阶段7 · 前端监控闭环**：任务详情 SSE + 时间线、错误高亮；列表分页在阶段6 已具备，本阶段与之协同验收。

## 自动化（当前仓库）

- 前端：`frontend/` 下执行 `npm run lint` 与 `npm run build`。
- 后端 SSE 契约：`tests/phase5/`（阶段5）覆盖；阶段7 不重复后端用例。

## 手工验收建议

1. 启动后端与前端，`VITE_API_BASE_URL` 指向后端。
2. 首页创建任务并跳转详情：时间线应出现 **加载历史 → 实时推送中** 状态提示，事件按 **seq** 递增。
3. **error** 类事件行左侧红色强调；**replan** 琥珀色强调。
4. 打开浏览器开发者工具网络：`events/stream` 为 `text/event-stream`；页面无需密钥请求头。
5. 任务进入终态后，提示变为 **事件流已结束**；计划区与状态与后端一致（含 `invalidateQueries` + 运行中轮询）。

## 文件索引（实现）

| 区域 | 路径 |
|------|------|
| SSE 消费 | `frontend/src/api/sse.ts` |
| 分帧解析 | `frontend/src/lib/sseParse.ts` |
| 合并逻辑 | `frontend/src/hooks/useTaskTimeline.ts` |
| UI | `frontend/src/components/task/TaskTimeline.tsx`、`TaskEventRow.tsx` |
| 页面 | `frontend/src/pages/TaskDetailPage.tsx` |
