/**
 * 会话资源 API 请求函数（与 API.md §3 对齐）。
 */

import { del, get, patch, post } from '@/api/client'
import type { OkResponse } from '@/types/api'
import type {
  Message,
  MessageCreateBody,
  MessageUpdateBody,
  MessagesListResponse,
  SessionContextResponse,
  SessionCreateBody,
  SessionCreateResponse,
  SessionDetail,
  SessionListResponse,
  SessionPatchBody,
} from '@/types/session'

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

/** TanStack Query 缓存键：`GET .../sessions/{id}/context`。 */
export function sessionContextQueryKey(sessionId: string) {
  return ['session', sessionId, 'context'] as const
}

/** 获取会话上下文预览（黑板、规划侧消息窗口、token 粗估）。 */
export function getSessionContext(
  sessionId: string,
): Promise<SessionContextResponse> {
  return get<SessionContextResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/context`,
  )
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

/** 单页上限与后端 `GET .../messages` 的 `limit` 上界一致。 */
export const SESSION_MESSAGES_PAGE_SIZE_MAX = 500

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

/** 分页拉取该会话下全部消息（按创建/ id 升序合并），供对话区与上下文用量与整会话一致。 */
export async function fetchAllSessionMessages(
  sessionId: string,
): Promise<MessagesListResponse> {
  const limit = SESSION_MESSAGES_PAGE_SIZE_MAX
  const messages: Message[] = []
  let offset = 0
  for (;;) {
    const page = await getSessionMessages(sessionId, { limit, offset })
    messages.push(...page.messages)
    if (page.messages.length < limit) break
    offset += limit
  }
  return { messages }
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
