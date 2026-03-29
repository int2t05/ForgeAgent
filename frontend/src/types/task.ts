/**
 * 任务相关类型定义（与后端 Pydantic Schema / API.md 对齐）。
 */

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export type EventModule = 'planning' | 'memory' | 'tool' | 'execution'

export type EventKind =
  | 'plan_created'
  | 'step_start'
  | 'tool_call'
  | 'tool_result'
  | 'error'
  | 'replan'
  | (string & {})

/** 任务列表摘要项。 */
export interface TaskSummary {
  id: string
  session_id: string
  status: TaskStatus
  summary: string | null
  plan_version: number
  created_at: string
  updated_at: string
}

/** 任务详情（含可选 plan 结构）。 */
export interface TaskDetail {
  id: string
  session_id: string
  status: TaskStatus
  summary: string | null
  plan_version: number
  plan: Record<string, unknown> | null
  created_at: string
  updated_at: string
  error_message: string | null
}

/** 单条可观测事件。 */
export interface TaskEvent {
  seq: number
  ts: string
  module: EventModule
  kind: EventKind
  payload: Record<string, unknown> | null
}

/** POST /tasks 请求体。 */
export interface TaskCreateBody {
  session_id: string
  user_message: string
}

/** POST /tasks 响应。 */
export interface TaskCreateResponse {
  task_id: string
  events_stream_path: string
}

/** GET /tasks 分页响应。 */
export interface TaskListResponse {
  items: TaskSummary[]
  total: number
}

/** GET /tasks/{id}/events 响应。 */
export interface TaskEventsResponse {
  events: TaskEvent[]
}
