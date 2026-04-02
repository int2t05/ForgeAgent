/**
 * 任务执行中：对话区底部 ReAct / 总结 的流式块（按轮次 Thought → Action 交替，再流式正文）。
 */

import {
  Fragment,
  lazy,
  memo,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type {
  ComposerRoundSegment,
  ComposerToolActionPanel,
} from '@/utils/foldComposerLlmStream'

const ChatMarkdown = lazy(() =>
  import('@/components/chat/ChatMarkdown').then((m) => ({ default: m.ChatMarkdown })),
)

const codeBlockPreClass =
  'max-h-[min(28rem,55vh)] overflow-y-auto rounded-md border border-neutral-700/40 bg-neutral-900/90 px-3 py-2.5 font-mono text-xs leading-relaxed text-neutral-100 whitespace-pre-wrap break-words [overflow-wrap:anywhere]'

const LlmStreamFold = memo(function LlmStreamFold({
  title,
  body,
  children,
}: {
  title: string
  body?: string
  children?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const preRef = useRef<HTMLPreElement>(null)
  const hasBody = Boolean(body?.trim())

  useEffect(() => {
    if (!open || !hasBody) return
    const el = preRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [body, open, hasBody])

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
          <div className="mt-2 space-y-3">
            {hasBody ? (
              <pre ref={preRef} className="fa-chat-thinking-pre">
                {body}
              </pre>
            ) : null}
            {children}
          </div>
        </details>
      </div>
    </div>
  )
})

/** write 正文：默认仅前 N 行，可展开全文。 */
const WriteContentPreview = memo(function WriteContentPreview({
  title,
  content,
  previewLines,
}: {
  title?: string
  content: string
  previewLines: number
}) {
  const lines = content.split(/\r?\n/)
  const hasMore = lines.length > previewLines
  const [expanded, setExpanded] = useState(false)
  const shown = !hasMore || expanded ? content : lines.slice(0, previewLines).join('\n')

  return (
    <div>
      {title ? <p className="mb-1 font-medium text-neutral-600 text-xs">{title}</p> : null}
      <pre className={codeBlockPreClass}>{shown}</pre>
      {hasMore ? (
        <button
          type="button"
          className="fa-link mt-1.5 text-xs"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '收起' : `展开全文（共 ${lines.length} 行）`}
        </button>
      ) : null}
    </div>
  )
})

const ToolActionPanelView = memo(function ToolActionPanelView({
  panel,
}: {
  panel: ComposerToolActionPanel
}) {
  if (panel.variant === 'plain') {
    return (
      <div className="text-neutral-700 text-xs leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
        {panel.title ? (
          <p className="mb-1 font-medium text-neutral-600">{panel.title}</p>
        ) : null}
        {panel.content}
      </div>
    )
  }

  if (panel.collapsible) {
    return (
      <details className="rounded-md border border-neutral-200 bg-neutral-50/80">
        <summary className="cursor-pointer select-none px-2 py-2 font-medium text-neutral-700 text-xs">
          {panel.title || '内容'}
        </summary>
        <pre className={`${codeBlockPreClass} m-2 mt-0`}>{panel.content}</pre>
      </details>
    )
  }

  if (panel.previewLines != null && panel.previewLines > 0) {
    return (
      <WriteContentPreview
        title={panel.title}
        content={panel.content}
        previewLines={panel.previewLines}
      />
    )
  }

  return (
    <div>
      {panel.title ? (
        <p className="mb-1 font-medium text-neutral-600 text-xs">{panel.title}</p>
      ) : null}
      <pre className={codeBlockPreClass}>{panel.content}</pre>
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
          {r.thought.trim() ? <LlmStreamFold title="Thought" body={r.thought} /> : null}
          {r.action ? (
            <LlmStreamFold
              title={`Action · ${r.action.subtitle?.trim() ? r.action.subtitle : '…'}`}
              body={
                r.action.panels && r.action.panels.length > 0 ? undefined : r.action.body
              }
            >
              {r.action.panels?.map((panel) => (
                <ToolActionPanelView key={`${r.action!.id}-${panel.id}`} panel={panel} />
              )) ?? null}
            </LlmStreamFold>
          ) : null}
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
