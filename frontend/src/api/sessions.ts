/**
 * 会话资源 API 请求函数（与 API.md §3 对齐）。
 */

import { get, post } from '@/api/client'
import type {
  MessagesListResponse,
  SessionCreateBody,
  SessionCreateResponse,
} from '@/types/session'

/** 创建新会话。 */
export function createSession(
  body?: SessionCreateBody,
): Promise<SessionCreateResponse> {
  return post<SessionCreateResponse>('/api/v1/sessions', body ?? {})
}

/** 获取会话消息列表（可选分页）。 */
export function getSessionMessages(
  sessionId: string,
  params?: { limit?: number; offset?: number },
): Promise<MessagesListResponse> {
  const query: Record<string, string> = {}
  if (params?.limit != null) query.limit = String(params.limit)
  if (params?.offset != null) query.offset = String(params.offset)
  return get<MessagesListResponse>(`/api/v1/sessions/${sessionId}/messages`, query)
}
