# 性能优化

## P0: 数据库优化

### append_event SELECT MAX 查询风暴

**问题**：每次追加事件都执行 `SELECT MAX(seq)`

**方案**：使用 INSERT RETURNING 原子获取序列号

```python
# 优化后
stmt = insert(TaskEvent).values(...).returning(TaskEvent.seq)
result = await db.execute(stmt)
allocated_seq = result.scalar_one()
```

### 连接复用

**问题**：SSE 轮询每 100ms 新建连接

**方案**：单长连接 + 批量预读

```python
async with AsyncSessionLocal() as db:
    while True:
        rows = await db.execute(select(...).limit(100))
        # 批量处理
```

## P1: 前端优化

### 细粒度状态订阅

**问题**：SSE 事件触发全组件重渲染

**方案**：Zustand 选择器 + React.memo

```typescript
// 原来
const liveTaskEvents = useComposerTaskStore(s => s.liveTaskEvents)

// 优化后 - 只订阅关心部分
const llmThinking = useComposerTaskStore(s => s.llmThinking)
const llmAnswer = useComposerTaskStore(s => s.llmAnswer)
```

## P2: Agent 执行优化

### 工具并行执行

```python
# 原来 - 串行
for tn, args in invocations:
    result = await run_single_tool(...)

# 优化后 - 并行
tasks = [run_single_tool(...) for tn, args in invocations]
results = await asyncio.gather(*tasks)
```

## 预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| DB 连接数/任务 | 200+ | 2-3 |
| SSE 轮询延迟 | 100ms | 50ms |
| 前端 CPU 占用 | 高 | 低 60% |
