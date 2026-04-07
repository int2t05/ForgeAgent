# API 文档

## 文档索引

| 文档 | 说明 |
|------|------|
| [REFERENCE.md](REFERENCE.md) | API 参考文档 |

## 基础信息

| 项目 | 值 |
|------|---|
| Base URL | `http://localhost:8000` |
| API 文档 | `http://localhost:8000/docs` |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

## 认证

当前版本无需认证，后续版本将支持 API Key 认证。

## 错误格式

```json
{
  "detail": "错误描述"
}
```

## SSE 事件流

SSE 端点返回 `text/event-stream`，每个事件格式：

```
event: <kind>
data: <json payload>

```

| kind | 说明 |
|------|------|
| `node_update` | 节点更新 |
| `plan_created` | 计划创建 |
| `step_start` | 步骤开始 |
| `tool_call` | 工具调用 |
| `tool_result` | 工具结果 |
| `step_end` | 步骤结束 |
| `message` | 助手消息 |
| `task_complete` | 任务完成 |
