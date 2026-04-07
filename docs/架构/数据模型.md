# 数据模型

## 核心实体

```
Session ─────┬──── Task ──────┬──── TaskEvent
             │                │
             └──── Message ───┘
```

## Session

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| user_id | TEXT | 用户标识 |
| title | TEXT | 会话标题 |
| blackboard_notes_json | TEXT | 黑板笔记 JSON |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

## Task

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键 (UUID) |
| session_id | INTEGER | 关联会话 |
| status | TEXT | pending/running/success/failed/cancelled |
| plan_version | INTEGER | 计划版本 |
| summary | TEXT | 执行总结 |
| error_message | TEXT | 错误信息 |
| created_at | DATETIME | 创建时间 |

## Message

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| session_id | INTEGER | 关联会话 |
| role | TEXT | user/assistant/system |
| content | TEXT | 消息内容 |
| created_at | DATETIME | 创建时间 |

## TaskEvent

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| task_id | TEXT | 关联任务 |
| module | TEXT | planning/execution/memory/llm |
| kind | TEXT | 事件类型 |
| payload_json | TEXT | 事件数据 |
| seq | INTEGER | 序列号 |
| created_at | DATETIME | 创建时间 |

## 任务状态流转

```
pending → running → success
              ↓
          failed/cancelled
```
