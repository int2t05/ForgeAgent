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

/** 获取会话消息列表。 */
export function getSessionMessages(sessionId: string): Promise<MessagesListResponse> {
  return get<MessagesListResponse>(`/api/v1/sessions/${sessionId}/messages`)
}
