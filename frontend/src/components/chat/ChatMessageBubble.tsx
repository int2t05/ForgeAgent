import {
  lazy,
  memo,
  Suspense,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { ChatSendArrowIcon, ChatStopIcon } from '@/components/chat/ChatPageIcons'
import { splitThinkingFromMessage } from '@/utils/parseMessageThinking'
import type { Message } from '@/types/session'

const ChatMarkdown = lazy(() =>
  import('@/components/chat/ChatMarkdown').then((m) => ({
    default: m.ChatMarkdown,
  })),
)

/** 已落库助手消息的思考段：小号辅文 + 链接式折叠（默认展开） */
const AssistantThinkingPanel = memo(function AssistantThinkingPanel({
  thinking,
}: {
  thinking: string
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className="fa-chat-block-thinking">
      <details
        className="fa-thinking-fold"
        open={open}
        onToggle={(e) => setOpen(e.currentTarget.open)}
      >
        <summary className="fa-thinking-summary">
          <span className="fa-chat-fold-link">Thought</span>
          <span className="fa-chat-fold-chevron" aria-hidden>
            ›
          </span>
        </summary>
        <pre className="fa-chat-thinking-pre">{thinking}</pre>
      </details>
    </div>
  )
})

/**
 * 持久化助手正文（思考已拆到 `AssistantThinkingPanel`）。
 * `revealAssistant`：保留供将来需要渐显时用；对话页任务结束后直接展示落库正文。
 */
const AssistantBubbleBody = memo(function AssistantBubbleBody({
  body,
  revealAssistant = false,
  hasThinking,
}: {
  body: string
  revealAssistant?: boolean
  hasThinking: boolean
}) {
  const main = body.trim()

  const [showBody, setShowBody] = useState(!revealAssistant)

  useEffect(() => {
    if (!revealAssistant) {
      setShowBody(true)
      return
    }
    setShowBody(false)
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const delayMs = reduced ? 0 : hasThinking ? 520 : 220
    const t = window.setTimeout(() => setShowBody(true), delayMs)
    return () => window.clearTimeout(t)
  }, [revealAssistant, hasThinking, body])

  const showPlaceholder =
    revealAssistant && !showBody && (Boolean(main) || hasThinking)

  return (
    <>
      {showPlaceholder ? (
        <p
          className="flex items-center gap-2 text-neutral-500"
          style={{ fontSize: 'var(--fa-chat-fs)' }}
        >
          <span className="inline-flex h-1.5 w-1.5 motion-safe:animate-pulse rounded-full bg-primary-400" />
          正在输出回复…
        </p>
      ) : null}
      {showBody && main ? (
        <div className={revealAssistant ? 'fa-chat-body-in' : undefined}>
          <Suspense
            fallback={
              <p className="whitespace-pre-wrap text-base text-neutral-500">{main}</p>
            }
          >
            <ChatMarkdown content={main} variant="assistant" />
          </Suspense>
        </div>
      ) : null}
    </>
  )
})

export interface MessageBubbleProps {
  message: Message
  revealAssistant?: boolean
  editing: boolean
  editDraft: string
  onEditDraftChange: (v: string) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  /** 回车提交：保存正文并重新执行任务。 */
  onSaveAndRerun: () => void
  actionsPending: boolean
  /** 生成中且为本轮用户消息时，悬停气泡右上角显示停止钮 */
  showStopOnHover?: boolean
  stopGenerationPending?: boolean
  onStopGeneration?: () => void
}

function shouldIgnoreUserBubbleEditClick(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return Boolean(target.closest('a, button, textarea, input, select, [contenteditable="true"]'))
}

/** 用户消息：点击进入单行编辑；回车≈重做；点外部取消；无按钮与说明文案。 */
export const MessageBubble = memo(function MessageBubble({
  message: m,
  revealAssistant = false,
  editing,
  editDraft,
  onEditDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveAndRerun,
  actionsPending,
  showStopOnHover = false,
  stopGenerationPending = false,
  onStopGeneration,
}: MessageBubbleProps) {
  const isUser = m.role === 'user'
  const canEditUser = isUser
  const editShellRef = useRef<HTMLDivElement>(null)
  const userEditTaRef = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    if (!editing || !isUser) return
    const el = userEditTaRef.current
    if (!el) return
    const id = requestAnimationFrame(() => {
      el.focus()
      const len = el.value.length
      el.setSelectionRange(len, len)
    })
    return () => cancelAnimationFrame(id)
  }, [editing, isUser, m.id])

  useEffect(() => {
    if (!editing || !isUser) return
    const onDocDown = (ev: MouseEvent) => {
      const t = ev.target
      if (!(t instanceof Node)) return
      if (editShellRef.current?.contains(t)) return
      onCancelEdit()
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [editing, isUser, onCancelEdit])

  const assistantParts = useMemo(
    () => (isUser ? null : splitThinkingFromMessage(m.content)),
    [isUser, m.content],
  )

  if (!isUser && assistantParts) {
    const { thinking, body } = assistantParts
    const hasT = Boolean(thinking)
    return (
      <>
        {thinking ? (
          <div className="fa-chat-thread">
            <AssistantThinkingPanel thinking={thinking} />
          </div>
        ) : null}
        <div className="fa-chat-thread">
          <div className="fa-chat-block-assistant">
            <AssistantBubbleBody
              body={body}
              revealAssistant={revealAssistant}
              hasThinking={hasT}
            />
          </div>
        </div>
      </>
    )
  }

  const userBubbleEditable = canEditUser && !editing && !showStopOnHover

  return (
    <div className="fa-chat-thread">
      <div
        className={`fa-chat-block-user${editing && isUser ? ' fa-chat-block-user--editing' : ''}${userBubbleEditable ? ' fa-chat-block-user--editable' : ''}${showStopOnHover ? ' fa-chat-block-user--stop-target' : ''}`}
        role={userBubbleEditable ? 'button' : undefined}
        tabIndex={userBubbleEditable ? 0 : undefined}
        aria-label={userBubbleEditable ? '点击编辑消息' : undefined}
        onClick={(e) => {
          if (!userBubbleEditable) return
          if (shouldIgnoreUserBubbleEditClick(e.target)) return
          const sel =
            typeof window !== 'undefined' ? (window.getSelection()?.toString() ?? '') : ''
          if (sel.trim().length > 0) return
          onStartEdit()
        }}
        onKeyDown={(e) => {
          if (!userBubbleEditable) return
          if (e.key !== 'Enter' && e.key !== ' ') return
          e.preventDefault()
          onStartEdit()
        }}
      >
        {showStopOnHover && isUser ? (
          <button
            type="button"
            className={`fa-chat-user-bubble-stop${stopGenerationPending ? ' fa-chat-user-bubble-stop--pending' : ''}`}
            aria-label="停止生成"
            disabled={stopGenerationPending}
            onClick={(e) => {
              e.stopPropagation()
              if (stopGenerationPending) return
              onStopGeneration?.()
            }}
          >
            {stopGenerationPending ? (
              <span className="fa-chat-send-spinner fa-chat-send-spinner--sm" aria-hidden />
            ) : (
              <ChatStopIcon className="size-4" />
            )}
          </button>
        ) : null}
        {editing && isUser ? (
          <div
            ref={editShellRef}
            className="flex min-w-0 items-center gap-2"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <textarea
              ref={userEditTaRef}
              value={editDraft}
              onChange={(e) => onEditDraftChange(e.target.value)}
              disabled={actionsPending}
              rows={1}
              className="fa-chat-user-edit-input min-h-0 flex-1 resize-none border-0 bg-transparent py-0.5 text-neutral-900 outline-none focus:ring-0 disabled:opacity-50"
              style={{ fontSize: 'var(--fa-chat-fs)', lineHeight: 'var(--fa-chat-lh)' }}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault()
                  onCancelEdit()
                  return
                }
                if (e.key !== 'Enter') return
                if (e.shiftKey) return
                if (e.nativeEvent.isComposing) return
                e.preventDefault()
                const t = editDraft.trim()
                if (!t || actionsPending) return
                onSaveAndRerun()
              }}
            />
            <button
              type="button"
              disabled={!editDraft.trim() || actionsPending}
              className="fa-chat-user-send-btn"
              aria-label="发送并重新执行"
              onClick={() => {
                const t = editDraft.trim()
                if (!t || actionsPending) return
                onSaveAndRerun()
              }}
            >
              {actionsPending ? (
                <span className="fa-chat-send-spinner fa-chat-send-spinner--sm" aria-hidden />
              ) : (
                <ChatSendArrowIcon className="size-[1.125rem]" />
              )}
            </button>
          </div>
        ) : (
          <Suspense
            fallback={<p className="whitespace-pre-wrap text-neutral-800">{m.content}</p>}
          >
            <ChatMarkdown content={m.content} variant="user" />
          </Suspense>
        )}
      </div>
    </div>
  )
})
