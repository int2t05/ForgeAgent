/**
 * 对话页：侧栏负责会话与重命名；主区全幅展示消息与输入（Agent 为主角）。
 */

import {
  Fragment,
  lazy,
  memo,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { ApiRequestError } from '@/api/client'
import { SessionListPanel } from '@/components/chat/SessionListPanel'
import { foldLlmStreamDeltas } from '@/lib/foldLlmStreamDeltas'
import { latestPlanStepsFromEvents } from '@/lib/normalizeTaskPlan'
import { splitThinkingFromMessage } from '@/lib/parseMessageThinking'

const ChatMarkdown = lazy(() =>
  import('@/components/chat/ChatMarkdown').then((m) => ({
    default: m.ChatMarkdown,
  })),
)
import { TaskPlanSteps } from '@/components/task/TaskPlanSteps'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { useSession } from '@/hooks/useSession'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
} from '@/hooks/usePendingComposerTask'
import { useComposerTaskStore } from '@/stores/composerTaskStore'
import { useSessionStore } from '@/stores/sessionStore'
import {
  deleteSession,
  deleteSessionMessage,
  getSession,
  getSessionMessages,
  patchSessionMessage,
} from '@/api/sessions'
import { createTask } from '@/api/tasks'
import type { PlanStep } from '@/lib/normalizeTaskPlan'
import type { Message } from '@/types/session'

const PlanStepsDialogBubble = memo(function PlanStepsDialogBubble({
  steps,
}: {
  steps: PlanStep[]
}) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[min(85%,42rem)] rounded-2xl rounded-bl-md border border-violet-100 bg-white px-4 py-3 text-[15px] leading-relaxed text-neutral-800 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
        <div className="mb-2 flex items-center gap-2">
          <span className="block font-medium text-[10px] text-neutral-500 uppercase tracking-[0.14em]">
            执行规划
          </span>
        </div>
        <TaskPlanSteps
          steps={steps}
          className="border-0 bg-transparent px-0 py-0 shadow-none"
        />
      </div>
    </div>
  )
})

export function ChatPage() {
  const queryClient = useQueryClient()
  const { sessionId, clearSession } = useSession()
  const [draft, setDraft] = useState('')
  /** 非空时表示待确认删除的会话 id（可与当前选中不同）。 */
  const [confirmDeleteSessionId, setConfirmDeleteSessionId] = useState<string | null>(null)
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [messageIdToDelete, setMessageIdToDelete] = useState<number | null>(null)
  const listEndRef = useRef<HTMLDivElement>(null)

  const sessionDetailQuery = useQuery({
    queryKey: ['session', sessionId, 'detail'],
    queryFn: () => getSession(sessionId!),
    enabled: Boolean(sessionId),
    retry: false,
  })

  useEffect(() => {
    const err = sessionDetailQuery.error
    if (err instanceof ApiRequestError && err.status === 404) {
      clearSession()
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
    }
  }, [sessionDetailQuery.error, clearSession, queryClient])

  const messagesQuery = useQuery({
    queryKey: ['session', sessionId, 'messages'],
    queryFn: () => getSessionMessages(sessionId!, { limit: 200 }),
    enabled: Boolean(sessionId),
  })

  const busy = usePendingComposerTaskBusy()
  const { pendingSessionId } = usePendingComposerTaskMeta()

  /** 本轮从对话发起的任务结束后，对最新一条助手消息做「先思考、再正文」的渐进展示。 */
  const [revealAssistantMessageId, setRevealAssistantMessageId] = useState<number | null>(
    null,
  )
  const prevBusyRef = useRef(false)
  /** 发送时记下会话：clearPending 后 pendingSessionId 已空，不能靠 store 判断是否本轮对话任务。 */
  const composerTargetSessionRef = useRef<string | null>(null)

  useEffect(() => {
    const wasBusy = prevBusyRef.current
    prevBusyRef.current = busy
    if (wasBusy && !busy) {
      if (sessionId && composerTargetSessionRef.current === sessionId) {
        const msgs = messagesQuery.data?.messages ?? []
        const lastAssistant = [...msgs].reverse().find((m) => m.role === 'assistant')
        const had = useComposerTaskStore.getState().lastComposerHadLlmStream
        if (!had) setRevealAssistantMessageId(lastAssistant?.id ?? null)
        else setRevealAssistantMessageId(null)
        useComposerTaskStore.getState().ackComposerStreamFlag()
      }
      composerTargetSessionRef.current = null
      return
    }
    if (busy) {
      setRevealAssistantMessageId(null)
    }
  }, [busy, sessionId, messagesQuery.data?.messages])

  const sendMutation = useMutation({
    mutationFn: (text: string) =>
      createTask({ session_id: sessionId!, user_message: text }),
    onSuccess: (res) => {
      setDraft('')
      if (sessionId) {
        composerTargetSessionRef.current = sessionId
        useComposerTaskStore.getState().setPending(res.task_id, sessionId)
      }
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const deleteSessionMutation = useMutation({
    mutationFn: (sid: string) => deleteSession(sid),
    onSuccess: (_data, sid) => {
      setConfirmDeleteSessionId(null)
      useComposerTaskStore.getState().clearStickyPlanForSession(sid)
      void queryClient.removeQueries({ queryKey: ['session', sid, 'messages'] })
      void queryClient.removeQueries({ queryKey: ['session', sid, 'detail'] })
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      if (sid === useSessionStore.getState().sessionId) clearSession()
    },
  })

  const patchMessageMutation = useMutation({
    mutationFn: (payload: { id: number; content: string }) =>
      patchSessionMessage(sessionId!, payload.id, { content: payload.content }),
    onSuccess: () => {
      setEditingMessageId(null)
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
    },
  })

  const deleteMessageMutation = useMutation({
    mutationFn: (mid: number) => deleteSessionMessage(sessionId!, mid),
    onSuccess: () => {
      setMessageIdToDelete(null)
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
    },
  })

  function submitComposer() {
    const t = draft.trim()
    if (!t || !sessionId || sendMutation.isPending || busy) return
    sendMutation.mutate(t)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    submitComposer()
  }

  function handleComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Enter') return
    if (e.shiftKey) return
    if (e.nativeEvent.isComposing) return
    e.preventDefault()
    submitComposer()
  }

  const messages: Message[] = messagesQuery.data?.messages ?? []
  const liveTaskEvents = useComposerTaskStore((s) => s.liveTaskEvents)
  const stickyPlansBySession = useComposerTaskStore((s) => s.stickyPlansBySession)
  const sseError = useComposerTaskStore((s) => s.sseError)
  const streamedLlm = useMemo(() => foldLlmStreamDeltas(liveTaskEvents), [liveTaskEvents])
  /** 进行中优先用实时事件里的规划；结束后 live 被清空，用按会话缓存的 sticky。 */
  const planForComposer = useMemo(() => {
    if (!sessionId) return null
    const fromLive = latestPlanStepsFromEvents(liveTaskEvents)
    if (fromLive?.length) return fromLive
    return stickyPlansBySession[sessionId] ?? null
  }, [sessionId, liveTaskEvents, stickyPlansBySession])

  /** 规划气泡插在最后一条用户消息之后（用户 → 规划 → 助手），与会话时间线一致。 */
  const lastUserMessageIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]!.role === 'user') return i
    }
    return -1
  }, [messages])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
  }, [
    messagesQuery.data?.messages.length,
    busy,
    streamedLlm.thinking.length,
    streamedLlm.answer.length,
  ])

  const sessionLoadError =
    sessionDetailQuery.error &&
    !(sessionDetailQuery.error instanceof ApiRequestError && sessionDetailQuery.error.status === 404)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ConfirmDialog
        open={confirmDeleteSessionId != null}
        title="删除会话"
        description="将删除本会话下的全部消息与任务记录，且无法恢复。若仍有任务在执行，将无法删除。"
        confirmLabel="删除会话"
        pending={deleteSessionMutation.isPending}
        onCancel={() =>
          !deleteSessionMutation.isPending && setConfirmDeleteSessionId(null)
        }
        onConfirm={() => {
          if (confirmDeleteSessionId)
            deleteSessionMutation.mutate(confirmDeleteSessionId)
        }}
      />

      <ConfirmDialog
        open={messageIdToDelete != null}
        title="删除消息"
        description="确定删除这条消息？"
        confirmLabel="删除"
        pending={deleteMessageMutation.isPending}
        onCancel={() =>
          !deleteMessageMutation.isPending && setMessageIdToDelete(null)
        }
        onConfirm={() => {
          if (messageIdToDelete != null) deleteMessageMutation.mutate(messageIdToDelete)
        }}
      />

      <div className="flex min-h-0 flex-1 flex-row">
        <SessionListPanel
          currentSessionHasRunningTask={
            Boolean(busy && sessionId && sessionId === pendingSessionId)
          }
          onRequestDeleteSession={(sid) => setConfirmDeleteSessionId(sid)}
          deleteSessionPending={deleteSessionMutation.isPending}
        />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col p-3 sm:p-4">
          {!sessionId && (
            <div className="fa-chat-canvas flex flex-1 flex-col items-center justify-center bg-violet-50/40 px-8">
              <div className="fa-reveal max-w-md text-center">
                <p className="font-display font-semibold text-neutral-800 text-xl tracking-tight">
                  选择或创建会话
                </p>
                <p className="mt-3 text-neutral-500 text-sm leading-relaxed">
                  在左侧新建或点选会话；每条会话右侧为「重命名」与「删除会话」。
                </p>
                <Link
                  to="/tasks"
                  className="fa-link mt-8 inline-block font-medium text-sm"
                >
                  查看任务与事件流 →
                </Link>
              </div>
            </div>
          )}

          {sessionId && (
            <div className="flex min-h-0 flex-1 flex-col gap-2">
              <div className="flex shrink-0 items-center justify-end">
                <Link
                  to="/tasks"
                  className="rounded-lg px-2 py-1 text-neutral-500 text-xs transition hover:bg-violet-100/50 hover:text-primary-700"
                >
                  任务与可观测事件
                </Link>
              </div>

              {(deleteSessionMutation.error ||
                patchMessageMutation.error ||
                deleteMessageMutation.error ||
                sessionLoadError ||
                messagesQuery.error) && (
                <div className="max-h-40 shrink-0 space-y-2 overflow-y-auto">
                  {deleteSessionMutation.error && (
                    <ErrorAlert
                      message="删除会话失败"
                      detail={
                        deleteSessionMutation.error instanceof Error
                          ? deleteSessionMutation.error.message
                          : '未知错误'
                      }
                    />
                  )}
                  {patchMessageMutation.error && (
                    <ErrorAlert
                      message="更新消息失败"
                      detail={
                        patchMessageMutation.error instanceof Error
                          ? patchMessageMutation.error.message
                          : '未知错误'
                      }
                    />
                  )}
                  {deleteMessageMutation.error && (
                    <ErrorAlert
                      message="删除消息失败"
                      detail={
                        deleteMessageMutation.error instanceof Error
                          ? deleteMessageMutation.error.message
                          : '未知错误'
                      }
                    />
                  )}
                  {sessionLoadError && (
                    <ErrorAlert
                      message="加载会话失败"
                      detail={
                        sessionDetailQuery.error instanceof Error
                          ? sessionDetailQuery.error.message
                          : '未知错误'
                      }
                    />
                  )}
                  {messagesQuery.error && (
                    <ErrorAlert
                      message="加载消息失败"
                      detail={
                        messagesQuery.error instanceof Error
                          ? messagesQuery.error.message
                          : '未知错误'
                      }
                    />
                  )}
                </div>
              )}

              <div className="fa-chat-canvas min-h-0">
                <div className="fa-chat-messages">
                  {messagesQuery.isLoading && <LoadingSpinner />}
                  {messages.length === 0 && !messagesQuery.isLoading && (
                    <p className="py-16 text-center text-neutral-400 text-sm leading-relaxed">
                      发送第一条消息开始对话
                    </p>
                  )}
                  {planForComposer?.length && lastUserMessageIndex < 0 ? (
                    <PlanStepsDialogBubble steps={planForComposer} />
                  ) : null}
                  {messages.map((m, i) => (
                    <Fragment key={m.id}>
                      <MessageBubble
                        message={m}
                        busy={busy}
                        revealAssistant={revealAssistantMessageId === m.id}
                        editing={editingMessageId === m.id}
                        editDraft={editDraft}
                        onEditDraftChange={setEditDraft}
                        onStartEdit={() => {
                          setEditingMessageId(m.id)
                          setEditDraft(m.content)
                        }}
                        onCancelEdit={() => setEditingMessageId(null)}
                        onSaveEdit={() =>
                          patchMessageMutation.mutate({
                            id: m.id,
                            content: editDraft.trim(),
                          })
                        }
                        savePending={patchMessageMutation.isPending}
                        onRequestDelete={() => setMessageIdToDelete(m.id)}
                      />
                      {planForComposer?.length && i === lastUserMessageIndex ? (
                        <PlanStepsDialogBubble steps={planForComposer} />
                      ) : null}
                    </Fragment>
                  ))}
                  {busy && (
                    <div className="flex justify-start">
                      <div className="max-w-[min(85%,42rem)] rounded-2xl rounded-bl-md border border-primary-100 bg-primary-50 px-4 py-3 text-primary-900 text-sm">
                        <span className="inline-flex items-center gap-2 font-medium">
                          <span className="relative flex h-2 w-2 shrink-0">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary-400 opacity-40" />
                            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary-500" />
                          </span>
                          生成中…
                        </span>
                        {streamedLlm.thinking ? (
                          <pre className="fa-thinking-body mt-3 max-h-40 overflow-y-auto rounded-lg border border-violet-200/80 bg-white/90 px-3 py-2 text-[12px] text-violet-950/90 whitespace-pre-wrap [overflow-wrap:anywhere]">
                            {streamedLlm.thinking}
                          </pre>
                        ) : null}
                        {streamedLlm.answer.trim() ? (
                          <div className="mt-2 rounded-lg border border-violet-200/80 bg-white/95 px-3 py-2 text-neutral-800">
                            <Suspense
                              fallback={
                                <p className="whitespace-pre-wrap text-neutral-400 text-sm">
                                  {streamedLlm.answer}
                                </p>
                              }
                            >
                              <ChatMarkdown
                                content={streamedLlm.answer}
                                variant="assistant"
                              />
                            </Suspense>
                          </div>
                        ) : null}
                        {sseError ? (
                          <p className="mt-2 text-red-600 text-xs">{sseError}</p>
                        ) : null}
                      </div>
                    </div>
                  )}
                  <div ref={listEndRef} />
                </div>

                <form onSubmit={handleSubmit} className="fa-chat-composer">
                  {sendMutation.error && (
                    <ErrorAlert
                      message="发送失败"
                      detail={
                        sendMutation.error instanceof Error
                          ? sendMutation.error.message
                          : '未知错误'
                      }
                    />
                  )}
                  <div className="mx-auto flex max-w-[52rem] flex-col gap-3 sm:flex-row sm:items-end">
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      placeholder="描述你想完成的目标…"
                      rows={busy || sendMutation.isPending ? 2 : 3}
                      disabled={busy || sendMutation.isPending}
                      className="fa-input min-h-[80px] flex-1 resize-none rounded-xl border-neutral-200/90"
                    />
                    <button
                      type="submit"
                      disabled={
                        !draft.trim() || busy || sendMutation.isPending || !sessionId
                      }
                      className="fa-btn-primary h-[48px] shrink-0 rounded-xl px-6 sm:min-w-[100px]"
                    >
                      {sendMutation.isPending || busy ? '处理中…' : '发送'}
                    </button>
                  </div>
                  <p className="mx-auto mt-3 max-w-[52rem] text-center text-[11px] text-neutral-400 leading-relaxed">
                    Enter 发送，Shift+Enter 换行
                  </p>
                </form>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const AssistantBubbleBody = memo(function AssistantBubbleBody({
  content,
  revealAssistant = false,
}: {
  content: string
  revealAssistant?: boolean
}) {
  const { thinking, body } = useMemo(() => splitThinkingFromMessage(content), [content])
  const main = body.trim() ? body : thinking ? '' : content

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
    const delayMs = reduced ? 0 : thinking ? 520 : 220
    const t = window.setTimeout(() => setShowBody(true), delayMs)
    return () => window.clearTimeout(t)
  }, [revealAssistant, thinking, content])

  const showPlaceholder =
    revealAssistant && !showBody && Boolean(main.trim() || (!thinking && content.trim()))

  const [thinkingOpen, setThinkingOpen] = useState(() => Boolean(revealAssistant && thinking))

  useEffect(() => {
    setThinkingOpen(Boolean(revealAssistant && thinking))
  }, [revealAssistant, thinking])

  return (
    <>
      {thinking ? (
        <details
          className="fa-thinking-fold mb-3"
          open={thinkingOpen}
          onToggle={(e) => setThinkingOpen(e.currentTarget.open)}
        >
          <summary className="fa-thinking-summary">
            思考过程
            <span className="fa-thinking-hint">点击展开</span>
          </summary>
          <div className="fa-thinking-body">{thinking}</div>
        </details>
      ) : null}
      {showPlaceholder ? (
        <p className="flex items-center gap-2 text-neutral-400 text-sm">
          <span className="inline-flex h-1.5 w-1.5 motion-safe:animate-pulse rounded-full bg-primary-400" />
          正在输出回复…
        </p>
      ) : null}
      {showBody && main.trim() ? (
        <div className={revealAssistant ? 'fa-chat-body-in' : undefined}>
          <Suspense
            fallback={
              <p className="whitespace-pre-wrap text-neutral-400 text-sm">{main}</p>
            }
          >
            <ChatMarkdown content={main} variant="assistant" />
          </Suspense>
        </div>
      ) : null}
    </>
  )
})

interface MessageBubbleProps {
  message: Message
  busy: boolean
  revealAssistant?: boolean
  editing: boolean
  editDraft: string
  onEditDraftChange: (v: string) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  savePending: boolean
  onRequestDelete: () => void
}

const MessageBubble = memo(function MessageBubble({
  message: m,
  busy,
  revealAssistant = false,
  editing,
  editDraft,
  onEditDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  savePending,
  onRequestDelete,
}: MessageBubbleProps) {
  const isUser = m.role === 'user'
  const canMutate = isUser && !busy

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[min(85%,42rem)] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
          isUser
            ? 'rounded-br-md bg-primary-600 text-white'
            : 'rounded-bl-md border border-violet-100 bg-white text-neutral-800'
        }`}
      >
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="block font-medium text-[10px] uppercase opacity-70 tracking-[0.14em]">
            {isUser ? '你' : '助手'}
          </span>
          {canMutate && !editing && (
            <div className="flex shrink-0 gap-1">
              <button
                type="button"
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${
                  isUser
                    ? 'text-white/90 hover:bg-white/10'
                    : 'text-neutral-500 hover:bg-neutral-100'
                }`}
                onClick={onStartEdit}
              >
                编辑
              </button>
              <button
                type="button"
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${
                  isUser ? 'text-red-100 hover:bg-red-500/30' : 'text-red-600'
                }`}
                onClick={onRequestDelete}
              >
                删除
              </button>
            </div>
          )}
        </div>
        {editing ? (
          <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
            <textarea
              value={editDraft}
              onChange={(e) => onEditDraftChange(e.target.value)}
              className="fa-input min-h-[80px] w-full resize-none rounded-lg text-sm text-neutral-900"
              disabled={savePending}
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="fa-btn-secondary rounded-lg py-1.5 px-3 text-xs"
                disabled={savePending}
                onClick={onCancelEdit}
              >
                取消
              </button>
              <button
                type="button"
                className="fa-btn-primary rounded-lg py-1.5 px-3 text-xs"
                disabled={savePending || !editDraft.trim()}
                onClick={onSaveEdit}
              >
                保存
              </button>
            </div>
          </div>
        ) : isUser ? (
          <Suspense
            fallback={
              <p className="whitespace-pre-wrap opacity-90">{m.content}</p>
            }
          >
            <ChatMarkdown content={m.content} variant="user" />
          </Suspense>
        ) : (
          <AssistantBubbleBody content={m.content} revealAssistant={revealAssistant} />
        )}
      </div>
    </div>
  )
})
