/**
 * 对话气泡内 Markdown 渲染（GFM）；默认安全、无 raw HTML。
 */

import { memo } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

const baseAssistant: Partial<Components> = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="fa-md-link underline decoration-primary-500/40 underline-offset-2 transition-colors hover:decoration-primary-600"
    >
      {children}
    </a>
  ),
}

const userAnchors: Partial<Components> = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="fa-md-link underline decoration-primary-500/40 underline-offset-2 transition-colors hover:decoration-primary-600"
    >
      {children}
    </a>
  ),
}

interface ChatMarkdownProps {
  content: string
  variant: 'assistant' | 'user'
}

export const ChatMarkdown = memo(function ChatMarkdown({
  content,
  variant,
}: ChatMarkdownProps) {
  if (!content.trim()) return null

  const className =
    variant === 'user' ? 'fa-md-chat fa-md-chat-user' : 'fa-md-chat'
  const extra = variant === 'user' ? userAnchors : baseAssistant

  return (
    <div className={className}>
      <Markdown remarkPlugins={[remarkGfm]} components={extra}>
        {content}
      </Markdown>
    </div>
  )
})
