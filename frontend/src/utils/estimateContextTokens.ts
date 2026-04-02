/**
 * 前端上下文用量粗算（与后端启发式同阶，仅用于 UI 进度环，非计费）。
 */

import type { Message } from '@/types/session'

/** 纯文本 → tokens 粗估（约每 3 字符 1 token，偏保守） */
export function estimateTokensFromText(text: string): number {
  if (!text) return 0
  return Math.max(1, Math.ceil(text.length / 3))
}

/** 会话消息列表估算进入模型的上下文量 */
export function estimateMessagesContextTokens(messages: Message[]): number {
  let n = 0
  for (const m of messages) {
    n += estimateTokensFromText(m.content)
    n += 4
  }
  return n
}
