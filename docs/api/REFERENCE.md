# API 参考

## 会话 API

### 创建会话

```
POST /api/v1/sessions
```

**请求体：**
```json
{
  "title": "会话标题"
}
```

**响应：**
```json
{
  "id": 1,
  "title": "会话标题",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 获取会话列表

```
GET /api/v1/sessions
```

**响应：**
```json
{
  "sessions": [
    {
      "id": 1,
      "title": "会话标题",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 获取会话详情

```
GET /api/v1/sessions/{id}
```

### 获取会话消息

```
GET /api/v1/sessions/{id}/messages
```

**响应：**
```json
{
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "用户消息",
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "助手回复",
      "created_at": "2024-01-01T00:00:01Z"
    }
  ]
}
```

---

## 任务 API

### 创建任务

```
POST /api/v1/tasks
```

**请求体：**
```json
{
  "session_id": 1,
  "user_message": "帮我写一个求阶乘的函数"
}
```

**响应：**
```json
{
  "task_id": "uuid-string",
  "events_stream_path": "/api/v1/tasks/uuid-string/events/stream"
}
```

### 获取任务列表

```
GET /api/v1/tasks
```

**查询参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| `session_id` | integer | 按会话筛选 |

### 获取任务详情

```
GET /api/v1/tasks/{id}
```

**响应：**
```json
{
  "id": "uuid-string",
  "session_id": 1,
  "status": "running",
  "plan_version": 1,
  "summary": null,
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 更新任务

```
PATCH /api/v1/tasks/{id}
```

**请求体：**
```json
{
  "status": "cancelled"
}
```

**状态值：** `pending`, `running`, `success`, `failed`, `cancelled`

### 获取任务事件

```
GET /api/v1/tasks/{id}/events
```

**查询参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| `after_seq` | integer | 返回 seq 之后的 events |

### SSE 事件流

```
GET /api/v1/tasks/{id}/events/stream
```

**响应：** `text/event-stream`

**事件格式：**

```json
{
  "seq": 1,
  "module": "planning",
  "kind": "plan_created",
  "payload": {
    "plan_version": 1,
    "steps": [
      {"id": "1", "title": "理解需求"},
      {"id": "2", "title": "实现代码"}
    ]
  }
}
```

---

## 工具 API

### 获取工具列表

```
GET /api/v1/tools
```

**响应：**
```json
{
  "tools": [
    {
      "name": "read_file",
      "description": "读取文件内容",
      "source": "builtin",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string"}
        }
      }
    }
  ]
}
```

---

## 设置 API

### 获取设置

```
GET /api/v1/settings
```

### 更新设置

```
PUT /api/v1/settings
```

**请求体：**
```json
{
  "mcp": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    }
  ],
  "skills_paths": ["/path/to/skills"]
}
```

### 校验 Skills 目录

```
POST /api/v1/settings/skills/validate
```

**请求体：**
```json
{
  "paths": ["/path/to/skills"]
}
```

**响应：**
```json
{
  "valid": true,
  "paths": [
    {"path": "/path/to/skills", "exists": true, "has_skill_md": true}
  ]
}
```

---

## 健康检查

### Health

```
GET /health
```

**响应：**
```json
{
  "status": "healthy"
}
```
