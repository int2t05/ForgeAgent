/**
 * 任务资源 API 请求函数（与 API.md §4 对齐）。
 */

import { del, get, patch, post } from '@/api/client'
import type { OkResponse } from '@/types/api'
import type {
  TaskCreateBody,
  TaskCreateResponse,
  TaskDetail,
  TaskEvent,
  TaskEventsResponse,
  TaskListResponse,
  TaskPatchBody,
} from '@/types/task'

/** 查询参数：任务列表。 */
export interface GetTasksParams {
  limit?: number
  offset?: number
  status?: string
  /** 仅返回该会话下的任务（按 created_at 倒序） */
  session_id?: string
}

/** 创建并启动任务。 */
export function createTask(body: TaskCreateBody): Promise<TaskCreateResponse> {
  return post<TaskCreateResponse>('/api/v1/tasks', body)
}

/** 获取任务分页列表。 */
export function getTasks(params?: GetTasksParams): Promise<TaskListResponse> {
  const query: Record<string, string> = {}
  if (params?.limit != null) query.limit = String(params.limit)
  if (params?.offset != null) query.offset = String(params.offset)
  if (params?.status) query.status = params.status
  if (params?.session_id) query.session_id = params.session_id
  return get<TaskListResponse>('/api/v1/tasks', query)
}

/** 获取单个任务详情。 */
export function getTask(taskId: string): Promise<TaskDetail> {
  return get<TaskDetail>(`/api/v1/tasks/${taskId}`)
}

/** 部分更新任务（如取消）。 */
export function patchTask(
  taskId: string,
  body: TaskPatchBody,
): Promise<TaskDetail> {
  return patch<TaskDetail>(
    `/api/v1/tasks/${encodeURIComponent(taskId)}`,
    body,
  )
}

/** 获取任务事件历史（支持增量 after_seq）。 */
export function getTaskEvents(
  taskId: string,
  afterSeq?: number,
  limit = 200,
): Promise<TaskEventsResponse> {
  const params: Record<string, string> = { limit: String(limit) }
  if (afterSeq != null) params.after_seq = String(afterSeq)
  return get<TaskEventsResponse>(`/api/v1/tasks/${taskId}/events`, params)
}

/**
 * 分页拉取任务内事件；`afterSeq` 有值时仅拉取其后的行（与 GET /events 一致）。
 * ReAct 等场景下单次 limit 易截断在 stream delta 中，需分页拉全量。
 */
export async function getAllTaskEvents(
  taskId: string,
  afterSeq?: number,
): Promise<TaskEvent[]> {
  const bySeq = new Map<number, TaskEvent>()
  let cursor: number | undefined = afterSeq
  for (;;) {
    const res = await getTaskEvents(taskId, cursor, 200)
    for (const e of res.events) {
      bySeq.set(e.seq, e)
    }
    if (res.events.length < 200) break
    cursor = res.events[res.events.length - 1]!.seq
  }
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
}

/** 删除已结束任务（running/pending 时后端返回 409）。 */
export function deleteTask(taskId: string): Promise<OkResponse> {
  return del<OkResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}`)
}
