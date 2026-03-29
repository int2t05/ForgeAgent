/**
 * 任务资源 API 请求函数（与 API.md §4 对齐）。
 */

import { get, post } from '@/api/client'
import type {
  TaskCreateBody,
  TaskCreateResponse,
  TaskDetail,
  TaskEventsResponse,
  TaskListResponse,
} from '@/types/task'

/** 查询参数：任务列表。 */
export interface GetTasksParams {
  limit?: number
  offset?: number
  status?: string
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
  return get<TaskListResponse>('/api/v1/tasks', query)
}

/** 获取单个任务详情。 */
export function getTask(taskId: string): Promise<TaskDetail> {
  return get<TaskDetail>(`/api/v1/tasks/${taskId}`)
}

/** 获取任务事件历史（支持增量 after_seq）。 */
export function getTaskEvents(
  taskId: string,
  afterSeq?: number,
): Promise<TaskEventsResponse> {
  const params: Record<string, string> = {}
  if (afterSeq != null) params.after_seq = String(afterSeq)
  return get<TaskEventsResponse>(`/api/v1/tasks/${taskId}/events`, params)
}
