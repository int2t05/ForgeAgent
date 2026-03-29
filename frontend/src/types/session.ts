/**
 * 会话与消息类型定义（与后端 Schema / API.md 对齐）。
 */

export type MessageRole = 'user' | 'assistant' | 'system'

/** 单条会话消息。 */
export interface Message {
  id: number
  role: MessageRole
  content: string
  created_at: string
}

/** POST /sessions 请求体。 */
export interface SessionCreateBody {
  title?: string
}

/** POST /sessions 响应。 */
export interface SessionCreateResponse {
  session_id: string
}

/** GET /sessions/{id}/messages 响应。 */
export interface MessagesListResponse {
  messages: Message[]
}
