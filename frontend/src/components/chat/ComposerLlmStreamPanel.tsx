/**
 * 任务执行中：对话区底部 ReAct / 总结 的流式块（按轮次 Thought → Action 交替，再流式正文）。
 */

import { Fragment, lazy, memo, Suspense, useEffect, useRef, useState } from 'react'
import type { ComposerActionBlock, ComposerRoundSegment } from '@/utils/foldComposerLlmStream'

const ChatMarkdown = lazy(() =>
  import('@/components/chat/ChatMarkdown').then((m) => ({ default: m.ChatMarkdown })),
)

const ThoughtRoundFold = memo(function ThoughtRoundFold({ body }: { body: string }) {
  const [open, setOpen] = useState(false)
  const preRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (!open || !body) return
    const el = preRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [body, open])

  return (
    <div className="fa-chat-thread">
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
          <pre ref={preRef} className="fa-chat-thinking-pre">
            {body}
          </pre>
        </details>
      </div>
    </div>
  )
})

const ActionFoldBlock = memo(function ActionFoldBlock({ block }: { block: ComposerActionBlock }) {
  const [open, setOpen] = useState(false)
  const preRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (!open || !block.body) return
    const el = preRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [block.body, open])

  const tool =
    block.subtitle != null && block.subtitle !== '' ? block.subtitle : '…'
  const title = `Action · ${tool}`

  return (
    <div className="fa-chat-thread">
      <div className="fa-chat-block-thinking">
        <details
          className="fa-thinking-fold"
          open={open}
          onToggle={(e) => setOpen(e.currentTarget.open)}
        >
          <summary className="fa-thinking-summary">
            <span className="fa-chat-fold-link">{title}</span>
            <span className="fa-chat-fold-chevron" aria-hidden>
              ›
            </span>
          </summary>
          <pre ref={preRef} className="fa-chat-thinking-pre">
            {block.body}
          </pre>
        </details>
      </div>
    </div>
  )
})

export interface ComposerLlmStreamPanelProps {
  variant?: 'streaming' | 'archived'
  rounds: ComposerRoundSegment[]
  answer: string
  sseError: string | null
}

export const ComposerLlmStreamPanel = memo(function ComposerLlmStreamPanel({
  variant = 'streaming',
  rounds,
  answer,
  sseError,
}: ComposerLlmStreamPanelProps) {
  return (
    <>
      {rounds.map((r) => (
        <Fragment key={r.id}>
          {r.thought.trim() ? (
            <ThoughtRoundFold body={r.thought} />
          ) : null}
          {r.action ? <ActionFoldBlock block={r.action} /> : null}
        </Fragment>
      ))}
      {variant === 'streaming' ? (
        <div className="fa-chat-thread">
          <div className="fa-chat-block-stream">
            <span className="fa-chat-stream-status">
              <span className="relative flex h-1.5 w-1.5 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary-400 opacity-40" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary-500" />
              </span>
              生成中
            </span>
            {answer.trim() ? (
              <div className="fa-chat-stream-nested">
                <Suspense
                  fallback={
                    <p
                      className="whitespace-pre-wrap text-neutral-500"
                      style={{ fontSize: 'var(--fa-chat-fs)' }}
                    >
                      {answer}
                    </p>
                  }
                >
                  <ChatMarkdown content={answer} variant="assistant" />
                </Suspense>
              </div>
            ) : null}
            {sseError ? (
              <p
                className="mt-1.5 text-red-600"
                style={{ fontSize: 'calc(var(--fa-chat-fs) * 0.88)' }}
              >
                {sseError}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  )
})
