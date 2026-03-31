/**
 * 会话列表/管理页：标题下的预览文案（纯文本，供多行截断展示）。
 */

import { splitThinkingFromMessage } from '@/utils/parseMessageThinking'

export function sessionListSnippetText(
  preview: string | null | undefined,
): string {
  if (preview == null || !preview.trim()) {
    return '打开对话'
  }
  const { body } = splitThinkingFromMessage(preview)
  const raw = body.trim() || preview.trim()
  return (
    raw
      .replace(/\r\n/g, '\n')
      .replace(/\n+/g, ' ')
      .replace(/[ \t]+/g, ' ')
      .trim() || '打开对话'
  )
}
