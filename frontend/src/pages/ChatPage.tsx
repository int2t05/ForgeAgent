/**
 * 对话页
 *
 * - 左：会话列表（SessionListPanel）
 * - 右：与 PRD 一致的四块能力在 UI 上的体现——记忆（消息列表）、规划（plan 气泡）、执行（任务流 + SSE 流式块）、归因到会话的任务入口
 * - 样式：`index.css` 中 `fa-chat-*`，正文宽度随主区域铺满
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
import { latestPlanStepsFromEvents, normalizePlanStepsFromUnknown } from '@/lib/normalizeTaskPlan'
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
import { deleteSession, getSession, getSessionMessages, patchSessionMessage } from '@/api/sessions'
import { createTask, getTask, getTaskEvents, getTasks } from '@/api/tasks'
import type { PlanStep } from '@/lib/normalizeTaskPlan'
import type { Message } from '@/types/session'

/** 空对话时的快捷选题（点击填入输入框） */
const CHAT_STARTER_PROMPTS = [
  '帮我把一个目标拆成可检查的执行步骤',
  '用两三句话说明 Plan-and-Execute 型 Agent 在做什么',
  '我要排查一个问题，请列出我该提供给你的信息清单',
] as const

/** 将 query / mutation 的 error 统一成展示文案 */
function errDetail(e: unknown): string {
  return e instanceof Error ? e.message : '未知错误'
}

/** 生成中仅在用户仍贴近列表底部时跟滚动；上移阅读时不再强制吸底，便于自由滚动。 */
function isNearScrollBottom(el: HTMLElement, thresholdPx = 96): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= thresholdPx
}

/**
 * 流式阶段：thinking 独立块且默认折叠（仍持续写入 DOM，展开可看）；
 * 正文在 `.fa-chat-stream-nested` 内单独滚动。
 */
const LlmStreamingPanel = memo(function LlmStreamingPanel({
  thinking,
  answer,
  sseError,
}: {
  thinking: string
  answer: string
  sseError: string | null
}) {
  const [thinkingOpen, setThinkingOpen] = useState(false)
  const thinkingPreRef = useRef<HTMLPreElement>(null)

  /** 展开时跟随流式追加，滚到底部便于阅读最新片段 */
  useEffect(() => {
    if (!thinkingOpen || !thinking) return
    const el = thinkingPreRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [thinking, thinkingOpen])

  return (
    <>
      {thinking ? (
        <div className="fa-chat-thread">
          <div className="fa-chat-block-thinking">
            <details
              className="fa-thinking-fold"
              open={thinkingOpen}
              onToggle={(e) => setThinkingOpen(e.currentTarget.open)}
            >
              <summary className="fa-thinking-summary">
                思考过程
                <span className="fa-thinking-hint">
                  {thinkingOpen
                    ? '点击折叠'
                    : `流式生成 · ${thinking.length} 字 · 点击展开`}
                </span>
              </summary>
              <pre
                ref={thinkingPreRef}
                className="fa-chat-thinking-pre mt-2 max-h-[min(24rem,50vh)] border-slate-200/80 border-t pt-2"
              >
                {thinking}
              </pre>
            </details>
          </div>
        </div>
      ) : null}
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
                className="whitespace-pre-wrap text-neutral-400"
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
    </>
  )
})

/** 已落库助手消息的思考段：独立气泡 + 折叠，与正文 `.fa-chat-block-assistant` 分离 */
const AssistantThinkingPanel = memo(function AssistantThinkingPanel({
  thinking,
}: {
  thinking: string
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="fa-chat-block-thinking">
      <details
        className="fa-thinking-fold"
        open={open}
        onToggle={(e) => setOpen(e.currentTarget.open)}
      >
        <summary className="fa-thinking-summary">
          思考过程
          <span className="fa-thinking-hint">点击展开</span>
        </summary>
        <pre className="fa-chat-thinking-pre mt-2 max-h-[min(24rem,50vh)] border-slate-200/80 border-t pt-2">
          {thinking}
        </pre>
      </details>
    </div>
  )
})

const PlanStepsDialogBubble = memo(function PlanStepsDialogBubble({
  steps,
}: {
  steps: PlanStep[]
}) {
  return (
    <div className="fa-chat-thread">
      <div className="fa-chat-block-plan">
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
  const messagesScrollRef = useRef<HTMLDivElement>(null)
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

  /** 本会话最近一次任务（用于刷新后从详情 API 恢复 plan_created 步骤） */
  const sessionTasksQuery = useQuery({
    queryKey: ['tasks', 'session', sessionId],
    queryFn: () => getTasks({ session_id: sessionId!, limit: 1, offset: 0 }),
    enabled: Boolean(sessionId),
  })
  const latestSessionTaskId = sessionTasksQuery.data?.items[0]?.id
  const latestSessionTaskDetailQuery = useQuery({
    queryKey: ['task', latestSessionTaskId],
    queryFn: () => getTask(latestSessionTaskId!),
    enabled: Boolean(latestSessionTaskId),
  })

  const planFromTaskDetail = useMemo(
    () =>
      normalizePlanStepsFromUnknown(latestSessionTaskDetailQuery.data?.plan ?? null),
    [latestSessionTaskDetailQuery.data?.plan],
  )

  /** 详情里 plan 偶发为空时，从事件表恢复 plan_created（修复刷新后步骤丢失） */
  const taskEventsPlanBootstrapQuery = useQuery({
    queryKey: ['task', latestSessionTaskId, 'events', 'plan-bootstrap'],
    queryFn: () => getTaskEvents(latestSessionTaskId!, undefined, 200),
    enabled:
      Boolean(latestSessionTaskId) &&
      latestSessionTaskDetailQuery.isSuccess &&
      !planFromTaskDetail?.length,
  })

  const planFromPersistedEvents = useMemo(
    () => latestPlanStepsFromEvents(taskEventsPlanBootstrapQuery.data?.events ?? []),
    [taskEventsPlanBootstrapQuery.data?.events],
  )

  const persistedPlanSteps = useMemo(() => {
    if (planFromTaskDetail?.length) return planFromTaskDetail
    if (planFromPersistedEvents?.length) return planFromPersistedEvents
    return null
  }, [planFromTaskDetail, planFromPersistedEvents])

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

  const startTaskMutation = useMutation({
    mutationFn: (args: { userMessage: string; reuseUserMessageId?: number }) =>
      createTask({
        session_id: sessionId!,
        user_message: args.userMessage,
        ...(args.reuseUserMessageId != null
          ? { reuse_user_message_id: args.reuseUserMessageId }
          : {}),
      }),
    onSuccess: (res) => {
      setDraft('')
      setEditingMessageId(null)
      if (sessionId) {
        composerTargetSessionRef.current = sessionId
        useComposerTaskStore.getState().setPending(res.task_id, sessionId)
      }
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks', 'session', sessionId] })
    },
  })

  const deleteSessionMutation = useMutation({
    mutationFn: (sid: string) => deleteSession(sid),
    onSuccess: (_data, sid) => {
      setConfirmDeleteSessionId(null)
      useComposerTaskStore.getState().clearStickyPlanForSession(sid)
      void queryClient.removeQueries({ queryKey: ['session', sid, 'messages'] })
      void queryClient.removeQueries({ queryKey: ['session', sid, 'detail'] })
      void queryClient.removeQueries({ queryKey: ['tasks', 'session', sid] })
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

  function submitComposer() {
    const t = draft.trim()
    if (!t || !sessionId || startTaskMutation.isPending || busy) return
    startTaskMutation.mutate({ userMessage: t })
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
  /**
   * 规划展示：SSE 实时 > 内存 sticky > 后端持久化（避免刷新后丢失）。
   * 新一轮 composer 进行中且尚无 SSE 规划时不用 persisted，以免闪现上一轮步骤。
   */
  const planForComposer = useMemo(() => {
    if (!sessionId) return null
    const fromLive = latestPlanStepsFromEvents(liveTaskEvents)
    if (fromLive?.length) return fromLive
    if (busy) return null
    const sticky = stickyPlansBySession[sessionId]
    if (sticky?.length) return sticky
    return persistedPlanSteps
  }, [sessionId, liveTaskEvents, stickyPlansBySession, busy, persistedPlanSteps])

  /** 规划气泡插在最后一条用户消息之后（用户 → 规划 → 助手），与会话时间线一致。 */
  const lastUserMessageIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]!.role === 'user') return i
    }
    return -1
  }, [messages])

  useEffect(() => {
    const root = messagesScrollRef.current
    const end = listEndRef.current
    if (!end) return
    if (busy && root && !isNearScrollBottom(root)) {
      return
    }
    end.scrollIntoView({ behavior: 'auto', block: 'end' })
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

      <div className="flex min-h-0 flex-1 flex-row">
        <SessionListPanel
          currentSessionHasRunningTask={
            Boolean(busy && sessionId && sessionId === pendingSessionId)
          }
          onRequestDeleteSession={(sid) => setConfirmDeleteSessionId(sid)}
          deleteSessionPending={deleteSessionMutation.isPending}
        />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col py-3 sm:py-4 px-2 sm:px-3">
          {!sessionId && (
            <div className="fa-chat-canvas flex flex-1 flex-col items-center justify-center bg-neutral-50/60 px-8">
              <div className="fa-reveal max-w-md text-center">
                <p className="font-display font-semibold text-neutral-800 text-xl tracking-tight">
                  选择或创建会话
                </p>
                <p className="mt-3 text-base text-neutral-500 leading-relaxed">
                  在左侧新建或点选会话；每条会话右侧为「重命名」与「删除会话」。
                </p>
                <Link
                  to="/tasks"
                  className="fa-link mt-8 inline-block font-medium text-base"
                >
                  查看任务与事件流 →
                </Link>
              </div>
            </div>
          )}

          {sessionId && (
            <div className="mt-2 min-h-0 flex-1 flex flex-col gap-2">
              {(deleteSessionMutation.error ||
                patchMessageMutation.error ||
                startTaskMutation.error ||
                sessionLoadError ||
                messagesQuery.error) && (
                <div className="max-h-40 shrink-0 space-y-2 overflow-y-auto">
                  {deleteSessionMutation.error ? (
                    <ErrorAlert message="删除会话失败" detail={errDetail(deleteSessionMutation.error)} />
                  ) : null}
                  {patchMessageMutation.error ? (
                    <ErrorAlert message="更新消息失败" detail={errDetail(patchMessageMutation.error)} />
                  ) : null}
                  {startTaskMutation.error ? (
                    <ErrorAlert message="启动任务失败" detail={errDetail(startTaskMutation.error)} />
                  ) : null}
                  {sessionLoadError ? (
                    <ErrorAlert message="加载会话失败" detail={errDetail(sessionDetailQuery.error)} />
                  ) : null}
                  {messagesQuery.error ? (
                    <ErrorAlert message="加载消息失败" detail={errDetail(messagesQuery.error)} />
                  ) : null}
                </div>
              )}

              <div className="fa-chat-canvas min-h-0">
                <div className="relative grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-2 border-neutral-200/80 border-b bg-neutral-50/40 px-3 py-2.5 sm:px-4">
                  <div aria-hidden className="min-w-0" />
                  <div className="min-w-0 text-center">
                    <p className="truncate font-medium text-base text-neutral-900">
                      {sessionDetailQuery.data?.title?.trim() || '新对话'}
                    </p>
                    <p className="fa-text-caption text-neutral-400">内容由 AI 生成，请核对重要信息</p>
                  </div>
                  <div className="flex justify-end">
                    <Link
                      to="/tasks"
                      className="fa-text-caption rounded-full px-3 py-1 text-neutral-500 transition hover:bg-white/90 hover:text-primary-800"
                    >
                      任务与事件
                    </Link>
                  </div>
                </div>
                <div ref={messagesScrollRef} className="fa-chat-messages">
                  {messagesQuery.isLoading && <LoadingSpinner />}
                  {messages.length === 0 && !messagesQuery.isLoading && (
                    <div className="flex flex-1 flex-col items-center justify-center px-4 pb-10 pt-6">
                      <h2 className="font-display text-center font-semibold text-2xl text-neutral-900 tracking-tight sm:text-3xl">
                        有什么我能帮你的吗？
                      </h2>
                      <p className="mx-auto mt-2 max-w-md text-center text-base text-neutral-500 leading-relaxed">
                        描述你的目标，Agent 将规划步骤并执行任务；可直接发送或先点选下方示例。
                      </p>
                      <div className="mt-8 flex w-full max-w-none flex-wrap justify-center gap-2 px-1">
                        {CHAT_STARTER_PROMPTS.map((t) => (
                          <button
                            key={t}
                            type="button"
                            disabled={busy || startTaskMutation.isPending}
                            onClick={() => setDraft(t)}
                            className="max-w-[min(100%,20rem)] rounded-full bg-neutral-100 px-4 py-2.5 text-left text-base text-neutral-700 leading-snug transition hover:bg-neutral-200/85 disabled:opacity-50"
                          >
                            {t}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {Boolean(planForComposer?.length) && lastUserMessageIndex < 0 ? (
                    <PlanStepsDialogBubble steps={planForComposer!} />
                  ) : null}
                  {messages.map((m, i) => (
                    <Fragment key={m.id}>
                      <MessageBubble
                        message={m}
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
                        onSaveAndRerun={() =>
                          startTaskMutation.mutate({
                            userMessage: editDraft.trim(),
                            reuseUserMessageId: m.id,
                          })
                        }
                        actionsPending={
                          patchMessageMutation.isPending || startTaskMutation.isPending
                        }
                      />
                      {Boolean(planForComposer?.length) && i === lastUserMessageIndex ? (
                        <PlanStepsDialogBubble steps={planForComposer!} />
                      ) : null}
                    </Fragment>
                  ))}
                  {busy ? (
                    <LlmStreamingPanel
                      thinking={streamedLlm.thinking}
                      answer={streamedLlm.answer}
                      sseError={sseError}
                    />
                  ) : null}
                  <div ref={listEndRef} />
                </div>

                <form onSubmit={handleSubmit} className="fa-chat-composer">
                  <div className="fa-chat-composer-inner">
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      placeholder="描述你想完成的目标…"
                      rows={1}
                      disabled={busy || startTaskMutation.isPending}
                      className="fa-chat-composer-input"
                    />
                    <button
                      type="submit"
                      disabled={
                        !draft.trim() || busy || startTaskMutation.isPending || !sessionId
                      }
                      className="fa-chat-composer-submit"
                    >
                      {startTaskMutation.isPending || busy ? '处理中…' : '发送'}
                    </button>
                  </div>
                  <p className="fa-chat-composer-hint">
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

/**
 * 持久化助手正文（思考已拆到 `AssistantThinkingPanel`）。
 * `revealAssistant`：本轮对话结束时正文短延迟渐显。
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
          className="flex items-center gap-2 text-neutral-400"
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
              <p className="whitespace-pre-wrap text-base text-neutral-400">{main}</p>
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
  revealAssistant?: boolean
  editing: boolean
  editDraft: string
  onEditDraftChange: (v: string) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  onSaveAndRerun: () => void
  actionsPending: boolean
}

/** 单条用户或助手消息；用户消息支持右上角编辑与「仅保存 / 保存并重新执行」。 */
const MessageBubble = memo(function MessageBubble({
  message: m,
  revealAssistant = false,
  editing,
  editDraft,
  onEditDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onSaveAndRerun,
  actionsPending,
}: MessageBubbleProps) {
  const isUser = m.role === 'user'
  const canEditUser = isUser

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

  return (
    <div className="fa-chat-thread">
      <div
        className={`fa-chat-block-user ${editing ? 'pr-3' : 'pr-8'}`}
      >
        {canEditUser && !editing ? (
          <button
            type="button"
            className="fa-chat-edit-corner"
            onClick={onStartEdit}
          >
            编辑
          </button>
        ) : null}
        {editing && isUser ? (
          <div className="space-y-2 pr-0" onClick={(e) => e.stopPropagation()}>
            <textarea
              value={editDraft}
              onChange={(e) => onEditDraftChange(e.target.value)}
              className="fa-input min-h-[88px] w-full resize-none rounded-md border-neutral-200 bg-white text-neutral-900"
              style={{ fontSize: 'var(--fa-chat-fs)' }}
              disabled={actionsPending}
            />
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              <button
                type="button"
                className="fa-btn-secondary rounded-lg px-3 py-1.5 text-sm"
                disabled={actionsPending}
                onClick={onCancelEdit}
              >
                取消
              </button>
              <button
                type="button"
                className="fa-btn-secondary rounded-lg px-3 py-1.5 text-sm"
                disabled={actionsPending || !editDraft.trim()}
                onClick={onSaveEdit}
              >
                仅保存
              </button>
              <button
                type="button"
                className="fa-btn-primary rounded-lg px-3 py-1.5 text-sm"
                disabled={actionsPending || !editDraft.trim()}
                onClick={onSaveAndRerun}
                title="将取消进行中的生成，并删除本条之后的助手回复后重新执行"
              >
                保存并重新执行
              </button>
            </div>
            <p className="fa-text-caption text-neutral-400">
              「保存并重新执行」将中断当前生成并清空本条之后的记录。
            </p>
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
