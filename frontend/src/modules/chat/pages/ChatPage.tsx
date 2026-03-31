/**
 * 对话页
 *
 * - 会话列表在全局 Sidebar 主导航下方
 * - 与 PRD 一致的四块能力在 UI 上的体现——记忆（消息列表）、规划（plan 气泡）、执行（任务流 + SSE 流式块）、归因到会话的任务入口
 * - 样式：`index.css` 中 `fa-chat-*`，正文宽度随主区域铺满
 */

import {
  Fragment,
  lazy,
  memo,
  Suspense,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { ApiRequestError } from '@/core/api/client'
import { errDetail } from '@/core/lib/errDetail'
import { foldLlmStreamDeltas } from '@/core/lib/foldLlmStreamDeltas'
import { latestPlanStepsFromEvents, normalizePlanStepsFromUnknown } from '@/core/lib/normalizeTaskPlan'
import { splitThinkingFromMessage } from '@/core/lib/parseMessageThinking'
import { TaskPlanSteps } from '@/modules/tasks/components/task/TaskPlanSteps'
import { LoadingSpinner } from '@/modules/shell/components/common/LoadingSpinner'
import { ErrorAlert } from '@/modules/shell/components/common/ErrorAlert'
import { useMainNavSidebarStore } from '@/modules/shell/stores/mainNavSidebarStore'
import { useSession } from '@/modules/sessions/hooks/useSession'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
} from '@/modules/tasks/hooks/usePendingComposerTask'
import { useComposerTaskStore } from '@/modules/tasks/stores/composerTaskStore'
import {
  createSession,
  getSession,
  getSessionMessages,
} from '@/modules/sessions/api/sessions'
import { createTask, getTask, getTaskEvents, getTasks } from '@/modules/tasks/api/tasks'
import type { PlanStep } from '@/core/lib/normalizeTaskPlan'
import type { Message } from '@/modules/sessions/types/session'

const ChatMarkdown = lazy(() =>
  import('@/modules/chat/components/chat/ChatMarkdown').then((m) => ({
    default: m.ChatMarkdown,
  })),
)

/** 顶栏：隐藏/显示最左侧主导航（圆角方壳 + 左侧约 1/3 处竖线，与常见侧栏抽屉图标一致） */
function ChatHeaderNavToggleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="4"
        y="5"
        width="16"
        height="14"
        rx="3"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M9 7.5v9"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** 顶栏：新会话（方壳内铅笔，与导航按钮同风格） */
function ChatHeaderNewSessionIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="4"
        y="4"
        width="16"
        height="16"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M12.25 16.25h5.25M15 7a1.9 1.9 0 012.7 2.7l-7 7-2.75.55.55-2.75 7-7z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** 圆形发送钮内向上箭头（界面不出现「发送」字样，依赖 `aria-label`） */
function ChatSendArrowIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M12 19V8m0 0-3.5 3.5M12 8l3.5 3.5"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** 空对话时的快捷选题（点击填入输入框） */
const CHAT_STARTER_PROMPTS = [
  '帮我把一个目标拆成可检查的执行步骤',
  '用两三句话说明 Plan-and-Execute 型 Agent 在做什么',
  '我要排查一个问题，请列出我该提供给你的信息清单',
] as const

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
                <span className="fa-chat-fold-link">思考过程</span>
                <span className="fa-chat-fold-chevron" aria-hidden>
                  ›
                </span>
              </summary>
              <pre ref={thinkingPreRef} className="fa-chat-thinking-pre">
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
    </>
  )
})

/** 已落库助手消息的思考段：小号辅文 + 链接式折叠 */
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
          <span className="fa-chat-fold-link">思考过程</span>
          <span className="fa-chat-fold-chevron" aria-hidden>
            ›
          </span>
        </summary>
        <pre className="fa-chat-thinking-pre">{thinking}</pre>
      </details>
    </div>
  )
})

const PlanStepsDialogBubble = memo(function PlanStepsDialogBubble({
  steps,
}: {
  steps: PlanStep[]
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="fa-chat-thread">
      <div className="fa-chat-block-plan">
        <details
          className="fa-thinking-fold"
          open={open}
          onToggle={(e) => setOpen(e.currentTarget.open)}
        >
          <summary className="fa-plan-summary">
            <span className="fa-chat-fold-link">执行计划</span>
            <span className="fa-chat-fold-chevron" aria-hidden>
              ›
            </span>
          </summary>
          <div className="fa-plan-body">
            <TaskPlanSteps
              steps={steps}
              className="border-0 bg-transparent px-0 py-0 shadow-none"
            />
          </div>
        </details>
      </div>
    </div>
  )
})

export function ChatPage() {
  const queryClient = useQueryClient()
  const { sessionId, setSessionId, clearSession } = useSession()
  const mainNavOpen = useMainNavSidebarStore((s) => s.open)
  const toggleMainNav = useMainNavSidebarStore((s) => s.toggle)
  const [draft, setDraft] = useState('')
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

  /** 本会话任务列表（倒序分页）；同时用于多轮对话下每条用户消息与任务的对应关系 */
  const sessionTasksQuery = useQuery({
    queryKey: ['tasks', 'session', sessionId],
    queryFn: () => getTasks({ session_id: sessionId!, limit: 100, offset: 0 }),
    enabled: Boolean(sessionId),
  })
  const latestSessionTaskId = sessionTasksQuery.data?.items[0]?.id
  const tasksChrono = useMemo(() => {
    const items = sessionTasksQuery.data?.items ?? []
    return [...items].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    )
  }, [sessionTasksQuery.data?.items])

  const taskPlanDetailQueries = useQueries({
    queries: tasksChrono.map((t) => ({
      queryKey: ['task', t.id] as const,
      queryFn: () => getTask(t.id),
      enabled: Boolean(sessionId) && tasksChrono.length > 0,
      staleTime: 60_000,
    })),
  })

  const planFromServerByTaskId = useMemo(() => {
    const map: Record<string, PlanStep[] | null> = {}
    tasksChrono.forEach((t, idx) => {
      const detail = taskPlanDetailQueries[idx]?.data
      if (!detail) {
        map[t.id] = null
        return
      }
      const fromApi = normalizePlanStepsFromUnknown(detail.plan ?? null)
      map[t.id] = fromApi?.length ? fromApi : null
    })
    return map
  }, [tasksChrono, taskPlanDetailQueries])

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
  const { pendingTaskId } = usePendingComposerTaskMeta()

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

  const createSessionHeaderMutation = useMutation({
    mutationFn: () => createSession(),
    onSuccess: (res) => {
      setSessionId(res.session_id)
      void queryClient.invalidateQueries({ queryKey: ['sessions', 'list'] })
    },
  })

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
  const plansByTaskId = useComposerTaskStore((s) => s.plansByTaskId)
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

  /**
   * 每条用户消息对应一轮任务：任务按创建时间排序后与 user 气泡顺序对齐；
   * 最后一轮用 pending/列表末任务，以兼容同一条用户消息重跑产生多任务。
   */
  const planStepsAfterUserMessageAt = useMemo(() => {
    return (messageIndex: number): PlanStep[] | null => {
      const row = messages[messageIndex]
      if (!row || row.role !== 'user') return null
      if (tasksChrono.length === 0) return null
      const userTurn =
        messages.slice(0, messageIndex + 1).filter((x) => x.role === 'user').length - 1
      const isLastUser = messageIndex === lastUserMessageIndex
      let tid: string | undefined
      if (isLastUser) {
        tid =
          busy && pendingTaskId
            ? pendingTaskId
            : tasksChrono[tasksChrono.length - 1]?.id
      } else {
        tid = tasksChrono[userTurn]?.id
      }
      if (!tid) return null
      if (isLastUser && busy && planForComposer?.length) return planForComposer
      const archived = plansByTaskId[tid]?.steps
      if (archived?.length) return archived
      const fromServer = planFromServerByTaskId[tid]
      if (fromServer?.length) return fromServer
      if (isLastUser && planForComposer?.length) return planForComposer
      return null
    }
  }, [
    messages,
    tasksChrono,
    lastUserMessageIndex,
    busy,
    pendingTaskId,
    planForComposer,
    plansByTaskId,
    planFromServerByTaskId,
  ])

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
      <div className="flex min-h-0 min-w-0 flex-1 flex-col py-3 sm:py-4 px-2 sm:px-3">
        <div className="mb-2 flex shrink-0 items-center gap-1.5 border-neutral-200/80 border-b bg-white/90 px-2 py-2.5 sm:px-3">
            <button
              type="button"
              onClick={toggleMainNav}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
              aria-label={mainNavOpen ? '隐藏导航栏' : '显示导航栏'}
              aria-expanded={mainNavOpen}
            >
              <ChatHeaderNavToggleIcon className="size-[1.375rem]" />
            </button>
            <button
              type="button"
              onClick={() => createSessionHeaderMutation.mutate()}
              disabled={createSessionHeaderMutation.isPending}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35 disabled:cursor-not-allowed disabled:opacity-45"
              aria-label="新会话"
            >
              <ChatHeaderNewSessionIcon className="size-[1.375rem]" />
            </button>
            <div className="min-w-0 flex-1 text-center">
              {sessionId ? (
                <>
                  <p className="truncate font-medium text-base text-neutral-900">
                    {sessionDetailQuery.data?.title?.trim() || '新对话'}
                  </p>
                  <p className="fa-text-caption text-neutral-500">内容由 AI 生成，请核对重要信息</p>
                </>
              ) : (
                <>
                  <p className="truncate font-medium text-base text-neutral-800">对话</p>
                  <p className="fa-text-caption text-neutral-500">
                    在左侧边栏「历史对话」中选会话，或点击「新会话」。
                  </p>
                </>
              )}
            </div>
          </div>

          {createSessionHeaderMutation.error ? (
            <div className="mb-2 shrink-0">
              <ErrorAlert
                message="创建会话失败"
                detail={errDetail(createSessionHeaderMutation.error)}
              />
            </div>
          ) : null}

          {!sessionId && (
            <div className="fa-chat-canvas flex flex-1 flex-col items-center justify-center bg-neutral-100/90 px-8">
              <div className="fa-reveal max-w-md text-center">
                <p className="font-display font-semibold text-neutral-800 text-xl tracking-tight">
                  选择或创建会话
                </p>
                <p className="mt-3 text-base text-neutral-500 leading-relaxed">
                  在左侧边栏「历史对话」中点选会话；悬停行可重命名或删除，双击标题可改名。
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
            <div className="min-h-0 flex-1 flex flex-col gap-2">
              {(startTaskMutation.error ||
                sessionLoadError ||
                messagesQuery.error) && (
                <div className="max-h-40 shrink-0 space-y-2 overflow-y-auto">
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
                            className="max-w-[min(100%,20rem)] rounded-full bg-neutral-100 px-4 py-2.5 text-left text-base text-neutral-700 leading-snug transition hover:bg-neutral-200/70 disabled:opacity-50"
                          >
                            {t}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {messages.map((m, i) => {
                    const planAfter = planStepsAfterUserMessageAt(i)
                    return (
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
                          onSaveAndRerun={() =>
                            startTaskMutation.mutate({
                              userMessage: editDraft.trim(),
                              reuseUserMessageId: m.id,
                            })
                          }
                          actionsPending={startTaskMutation.isPending}
                        />
                        {m.role === 'user' && planAfter?.length ? (
                          <PlanStepsDialogBubble steps={planAfter} />
                        ) : null}
                      </Fragment>
                    )
                  })}
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
                      aria-label={
                        startTaskMutation.isPending || busy ? '正在处理' : '发送'
                      }
                    >
                      {startTaskMutation.isPending || busy ? (
                        <span
                          className="fa-chat-send-spinner fa-chat-send-spinner--sm"
                          aria-hidden
                        />
                      ) : (
                        <ChatSendArrowIcon className="size-4" />
                      )}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
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

interface MessageBubbleProps {
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
}

function shouldIgnoreUserBubbleEditClick(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return Boolean(target.closest('a, button, textarea, input, select, [contenteditable="true"]'))
}

/** 用户消息：点击进入单行编辑；回车≈重做；点外部取消；无按钮与说明文案。 */
const MessageBubble = memo(function MessageBubble({
  message: m,
  revealAssistant = false,
  editing,
  editDraft,
  onEditDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveAndRerun,
  actionsPending,
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

  const userBubbleEditable = canEditUser && !editing

  return (
    <div className="fa-chat-thread">
      <div
        className={`fa-chat-block-user${editing && isUser ? ' fa-chat-block-user--editing' : ''}${userBubbleEditable ? ' fa-chat-block-user--editable' : ''}`}
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
