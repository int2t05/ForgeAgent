/**
 * 会话资源 API 请求函数（与 API.md §3 对齐）。
 */

import { del, get, patch, post } from '@/core/api/client'
import type { OkResponse } from '@/core/types/api'
import type {
  Message,
  MessageCreateBody,
  MessageUpdateBody,
  MessagesListResponse,
  SessionCreateBody,
  SessionCreateResponse,
  SessionDetail,
  SessionListResponse,
  SessionPatchBody,
} from '@/modules/sessions/types/session'

/** 分页列出会话。 */
export function getSessions(params?: {
  limit?: number
  offset?: number
}): Promise<SessionListResponse> {
  const query: Record<string, string> = {}
  if (params?.limit != null) query.limit = String(params.limit)
  if (params?.offset != null) query.offset = String(params.offset)
  return get<SessionListResponse>('/api/v1/sessions', query)
}

/** 创建新会话。 */
export function createSession(
  body?: SessionCreateBody,
): Promise<SessionCreateResponse> {
  return post<SessionCreateResponse>('/api/v1/sessions', body ?? {})
}

/** 获取会话元数据。 */
export function getSession(sessionId: string): Promise<SessionDetail> {
  return get<SessionDetail>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`)
}

/** 更新会话元数据。 */
export function patchSession(
  sessionId: string,
  body: SessionPatchBody,
): Promise<SessionDetail> {
  return patch<SessionDetail>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    body,
  )
}

/** 获取会话消息列表（可选分页）。 */
export function getSessionMessages(
  sessionId: string,
  params?: { limit?: number; offset?: number },
): Promise<MessagesListResponse> {
  const query: Record<string, string> = {}
  if (params?.limit != null) query.limit = String(params.limit)
  if (params?.offset != null) query.offset = String(params.offset)
  return get<MessagesListResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`,
    query,
  )
}

/** 追加一条会话消息。 */
export function postSessionMessage(
  sessionId: string,
  body: MessageCreateBody,
): Promise<Message> {
  return post<Message>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`,
    body,
  )
}

/** 更新一条消息正文。 */
export function patchSessionMessage(
  sessionId: string,
  messageId: number,
  body: MessageUpdateBody,
): Promise<Message> {
  return patch<Message>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages/${messageId}`,
    body,
  )
}

/** 删除一条消息。 */
export function deleteSessionMessage(
  sessionId: string,
  messageId: number,
): Promise<OkResponse> {
  return del<OkResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages/${messageId}`,
  )
}

/** 删除会话及其下属数据（进行中任务存在时后端返回 409）。 */
export function deleteSession(sessionId: string): Promise<OkResponse> {
  return del<OkResponse>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`)
}
