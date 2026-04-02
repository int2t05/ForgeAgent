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
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type Query,
  type QueryClient,
} from '@tanstack/react-query'
import { Link } from 'react-router'
import { ApiRequestError } from '@/api/client'
import { errDetail } from '@/utils/errDetail'
import {
  composerRoundsHaveContent,
  composerRoundsPayloadLength,
  foldComposerLlmStreamForBusy,
  foldComposerLlmStreamForFreeze,
} from '@/utils/foldComposerLlmStream'
import {
  derivePlanTodoProgress,
  latestPlanStepsFromEvents,
  normalizePlanStepsFromUnknown,
} from '@/utils/normalizeTaskPlan'
import { splitThinkingFromMessage } from '@/utils/parseMessageThinking'
import { ChatWorkspaceSidebar } from '@/components/chat/ChatWorkspaceSidebar'
import { ComposerContextRing } from '@/components/chat/ComposerContextRing'
import { ComposerLlmStreamPanel } from '@/components/chat/ComposerLlmStreamPanel'
import { TaskPlanSteps } from '@/components/task/TaskPlanSteps'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { useMainNavSidebarStore } from '@/store/mainNavSidebarStore'
import { useSession } from '@/hooks/useSession'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
} from '@/hooks/usePendingComposerTask'
import { useComposerTaskStore } from '@/store/composerTaskStore'
import {
  createSession,
  fetchAllSessionMessages,
  getSession,
  getSessionContext,
  sessionContextQueryKey,
} from '@/api/sessions'
import {
  createTask,
  getAllTaskEvents,
  getTask,
  getTaskEvents,
  getTasks,
  patchTask,
} from '@/api/tasks'
import { LLM_CONTEXT_WINDOW_TOKENS } from '@/config/env'
import type { PlanStep, PlanTodoProgress } from '@/utils/normalizeTaskPlan'
import {
  estimateMessagesContextTokens,
  estimateTokensFromText,
} from '@/utils/estimateContextTokens'
import { TERMINAL_STATUSES } from '@/constants/task'
import type { Message } from '@/types/session'
import type { TaskDetail, TaskEvent } from '@/types/task'

const ChatMarkdown = lazy(() =>
  import('@/components/chat/ChatMarkdown').then((m) => ({
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

/** 顶栏：切换右侧工作区侧栏（与对话区并排） */
function ChatHeaderWorkspaceIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="3.25"
        y="4.75"
        width="17.5"
        height="14.5"
        rx="2.25"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M9.25 4.75v14.5"
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

/** 生成中：圆钮内的「停止」方块（与常见对话产品一致） */
function ChatStopIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="8"
        y="8"
        width="8"
        height="8"
        rx="2"
        fill="currentColor"
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

/**
 * 停止任务后尽量恢复「本轮规划步骤」：内存 live/sticky → clearPending 归档 → 任务详情 → 事件拉取。
 * 顺序与 clearPending 交互敏感，勿在 clear 前遗漏 live 快照。
 */
async function resolvePlanStepsAfterComposerStop(
  taskId: string,
  queryClient: QueryClient,
): Promise<PlanStep[] | null> {
  const store = useComposerTaskStore.getState()
  const fromLive = latestPlanStepsFromEvents(store.liveTaskEvents)
  const pendSid = store.pendingSessionId
  const fromSticky =
    pendSid != null ? store.stickyPlansBySession[pendSid] : undefined
  const snapshot =
    fromLive?.length ? fromLive : fromSticky?.length ? fromSticky : null

  store.clearPending()

  const archived = useComposerTaskStore.getState().plansByTaskId[taskId]?.steps
  if (archived?.length) return archived
  if (snapshot?.length) return snapshot

  try {
    const detail = await queryClient.fetchQuery({
      queryKey: ['task', taskId],
      queryFn: () => getTask(taskId),
    })
    const fromApi = normalizePlanStepsFromUnknown(detail.plan ?? null)
    if (fromApi?.length) return fromApi
  } catch {
    /* 网络/404 时继续尝试事件 */
  }

  try {
    const { events } = await getTaskEvents(taskId, undefined, 200)
    return latestPlanStepsFromEvents(events)
  } catch {
    return null
  }
}

/** 生成中仅在用户仍贴近列表底部时跟滚动；上移阅读时不再强制吸底，便于自由滚动。 */
function isNearScrollBottom(el: HTMLElement, thresholdPx = 96): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= thresholdPx
}

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

/** 聊天气泡区顶条：与 ``fa-chat-messages`` 同水平内边距（左缘与消息对齐），可折叠，状态写入 localStorage */
const ChatHeaderPlanTodos = memo(function ChatHeaderPlanTodos({
  steps,
  todoProgress,
}: {
  steps: PlanStep[]
  todoProgress: PlanTodoProgress
}) {
  const [open, setOpen] = useState(() => {
    if (typeof window === 'undefined') return true
    return window.localStorage.getItem('fa-chat-plan-todos-open') !== '0'
  })

  useEffect(() => {
    window.localStorage.setItem('fa-chat-plan-todos-open', open ? '1' : '0')
  }, [open])

  const { done, total } = useMemo(() => {
    const t = steps.length
    const d = steps.filter((s) => todoProgress.statusByStepId[s.id] === 'done').length
    return { done: d, total: t }
  }, [steps, todoProgress])

  return (
    <div
      className="shrink-0 border-neutral-200/70 border-b bg-white/95 px-3 pb-1 pt-1 sm:px-5"
      aria-label="当前任务步骤"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full min-w-0 items-center gap-2 rounded-md py-0.5 text-left text-neutral-700 transition hover:bg-neutral-100/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
        aria-expanded={open}
      >
        <span className="font-medium text-[0.6875rem] text-neutral-500 uppercase tracking-wide">
          To-dos
        </span>
        <span className="font-medium text-neutral-400 text-xs tabular-nums">
          {done}/{total}
        </span>
        <span
          className={`ml-auto shrink-0 text-neutral-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          aria-hidden
        >
          <svg
            className="size-4"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M6 9l6 6 6-6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>
      {open ? (
        <div className="mt-0.5 max-h-[min(38vh,10rem)] overflow-y-auto overscroll-contain border-neutral-200/80 border-l pl-2.5">
          <TaskPlanSteps
            steps={steps}
            todoProgress={todoProgress}
            className="border-0 bg-transparent px-0 py-0 shadow-none [font-size:0.8125rem] [--fa-chat-fs:0.8125rem] [--fa-chat-lh:1.45]"
          />
        </div>
      ) : null}
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
  /** 打开或切换到会话后吸底一次，避免「进行中任务 + 初始 scrollTop=0」被误判为用户上卷而不滚动。 */
  const forceScrollToLatestRef = useRef(false)
  const prevSessionIdForScrollRef = useRef<string | null | undefined>(undefined)
  const prevBusyRef = useRef(false)
  /** 发送或从服务端恢复进行中任务时记下会话：clearPending 后仅靠 store 无法判断是否本轮对话。 */
  const composerTargetSessionRef = useRef<string | null>(null)

  const [workspaceSidebarOpen, setWorkspaceSidebarOpen] = useState(() => {
    if (typeof window === 'undefined') return true
    return window.localStorage.getItem('fa-chat-workspace-sidebar') !== '0'
  })

  useEffect(() => {
    window.localStorage.setItem(
      'fa-chat-workspace-sidebar',
      workspaceSidebarOpen ? '1' : '0',
    )
  }, [workspaceSidebarOpen])

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
    queryFn: () => fetchAllSessionMessages(sessionId!),
    enabled: Boolean(sessionId),
  })

  /** 本会话任务列表（倒序分页）；同时用于多轮对话下每条用户消息与任务的对应关系 */
  const sessionTasksQuery = useQuery({
    queryKey: ['tasks', 'session', sessionId],
    queryFn: () => getTasks({ session_id: sessionId!, limit: 100, offset: 0 }),
    enabled: Boolean(sessionId),
  })

  /**
   * 全页刷新或新开标签后 Zustand 无 pendingTaskId，SSE 不会挂载，界面既无「生成中」也无法补拉流式片段。
   * 若本会话最新任务仍在 running/pending，则以任务详情为准恢复 setPending（避免列表缓存滞后误重连）。
   */
  useEffect(() => {
    let cancelled = false
    async function hydratePendingFromActiveTask() {
      if (!sessionId || !sessionTasksQuery.isSuccess) return
      const items = sessionTasksQuery.data?.items ?? []
      const head = items[0]
      if (!head || (head.status !== 'running' && head.status !== 'pending')) return
      if (useComposerTaskStore.getState().pendingTaskId === head.id) return
      try {
        const detail = await queryClient.fetchQuery({
          queryKey: ['task', head.id],
          queryFn: () => getTask(head.id),
        })
        if (cancelled) return
        if (detail.status !== 'running' && detail.status !== 'pending') return
        if (useComposerTaskStore.getState().pendingTaskId === head.id) return
        composerTargetSessionRef.current = sessionId
        useComposerTaskStore.getState().setPending(head.id, sessionId)
      } catch {
        /* 忽略校验失败，不阻塞对话 */
      }
    }
    void hydratePendingFromActiveTask()
    return () => {
      cancelled = true
    }
  }, [
    sessionId,
    sessionTasksQuery.isSuccess,
    sessionTasksQuery.data?.items?.[0]?.id,
    sessionTasksQuery.data?.items?.[0]?.status,
    queryClient,
  ])

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
      refetchInterval: (query: Query<TaskDetail, Error, TaskDetail, readonly ['task', string]>) => {
        const row = query.state.data
        if (!row || TERMINAL_STATUSES.has(row.status)) return false
        const tid = query.queryKey[1]
        if (tid === useComposerTaskStore.getState().pendingTaskId) {
          return false
        }
        return 5000
      },
    })),
  })

  /** 用于消息区 To-do 进度；与详情查询并行，刷新后仍可自事件推导勾选态 */
  const taskEventsProgressQueries = useQueries({
    queries: tasksChrono.map((t) => ({
      queryKey: ['task', t.id, 'events', 'chat-progress'] as const,
      queryFn: () => getTaskEvents(t.id, undefined, 400),
      enabled: Boolean(sessionId) && tasksChrono.length > 0,
      staleTime: 60_000,
    })),
  })

  const taskEventsByIdForChat = useMemo(() => {
    const m: Record<string, TaskEvent[]> = {}
    tasksChrono.forEach((t, i) => {
      const ev = taskEventsProgressQueries[i]?.data?.events
      if (ev?.length) m[t.id] = ev
    })
    return m
  }, [tasksChrono, taskEventsProgressQueries])

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

  /** 与会话列表首条（最新）任务对应的详情，复用 taskPlanDetailQueries 避免重复 GET /task */
  const latestTaskDetailQuery = useMemo(() => {
    if (!latestSessionTaskId || tasksChrono.length === 0) return null
    const idx = tasksChrono.findIndex((t) => t.id === latestSessionTaskId)
    if (idx < 0) return null
    return taskPlanDetailQueries[idx] ?? null
  }, [latestSessionTaskId, tasksChrono, taskPlanDetailQueries])

  const planFromTaskDetail = useMemo(
    () => normalizePlanStepsFromUnknown(latestTaskDetailQuery?.data?.plan ?? null),
    [latestTaskDetailQuery?.data?.plan],
  )

  /** 详情里 plan 偶发为空时，从事件表恢复 plan_created（修复刷新后步骤丢失） */
  const taskEventsPlanBootstrapQuery = useQuery({
    queryKey: ['task', latestSessionTaskId, 'events', 'plan-bootstrap'],
    queryFn: () => getTaskEvents(latestSessionTaskId!, undefined, 200),
    enabled:
      Boolean(latestSessionTaskId) &&
      Boolean(latestTaskDetailQuery?.isSuccess) &&
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

  useEffect(() => {
    const wasBusy = prevBusyRef.current
    prevBusyRef.current = busy
    if (wasBusy && !busy) {
      if (sessionId && composerTargetSessionRef.current === sessionId) {
        useComposerTaskStore.getState().ackComposerStreamFlag()
      }
      composerTargetSessionRef.current = null
      return
    }
  }, [busy, sessionId])

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
        void queryClient.fetchQuery({
          queryKey: sessionContextQueryKey(sessionId),
          queryFn: () => getSessionContext(sessionId),
        })
      }
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks', 'session', sessionId] })
    },
  })

  const stopTaskMutation = useMutation({
    mutationFn: async () => {
      const tid = useComposerTaskStore.getState().pendingTaskId
      if (!tid) throw new Error('当前没有执行中的任务')
      return patchTask(tid, { status: 'cancelled' })
    },
    onSuccess: async (detail) => {
      const sid = sessionId!
      const taskId = detail.id
      const restored = detail.restored_user_message
      if (restored != null && restored !== '') setDraft(restored)

      const steps = await resolvePlanStepsAfterComposerStop(taskId, queryClient)
      if (
        restored != null &&
        restored !== '' &&
        steps != null &&
        steps.length > 0
      ) {
        useComposerTaskStore.getState().setDetachedComposerPlan({
          sessionId: sid,
          taskId,
          steps,
        })
      }

      await queryClient.invalidateQueries({ queryKey: ['session', sid, 'messages'] })
      await queryClient.invalidateQueries({ queryKey: ['task', taskId] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks', 'session', sid] })
    },
  })

  function submitComposer() {
    const t = draft.trim()
    if (!t || !sessionId || startTaskMutation.isPending || busy) return
    startTaskMutation.mutate({ userMessage: t })
  }

  /** 主按钮/回车：发送或停止生成（停止后正文由后端写入 `restored_user_message` 恢复到底栏）。 */
  function runComposerPrimaryAction() {
    if (!sessionId || startTaskMutation.isPending) return
    if (busy && pendingTaskId) {
      stopTaskMutation.mutate()
      return
    }
    submitComposer()
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    runComposerPrimaryAction()
  }

  function handleComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Enter') return
    if (e.shiftKey) return
    if (e.nativeEvent.isComposing) return
    e.preventDefault()
    runComposerPrimaryAction()
  }

  useEffect(() => {
    const d = useComposerTaskStore.getState().detachedComposerPlan
    if (d != null && sessionId != null && d.sessionId !== sessionId) {
      useComposerTaskStore.getState().clearDetachedComposerPlan()
    }
  }, [sessionId])

  const messages: Message[] = messagesQuery.data?.messages ?? []
  const liveTaskEvents = useComposerTaskStore((s) => s.liveTaskEvents)
  const stickyPlansBySession = useComposerTaskStore((s) => s.stickyPlansBySession)
  const plansByTaskId = useComposerTaskStore((s) => s.plansByTaskId)
  const detachedComposerPlan = useComposerTaskStore((s) => s.detachedComposerPlan)
  const sseError = useComposerTaskStore((s) => s.sseError)
  const composerStreamFreeze = useComposerTaskStore((s) => s.composerStreamFreeze)
  const streamedLlm = useMemo(
    () => foldComposerLlmStreamForBusy(liveTaskEvents, busy),
    [liveTaskEvents, busy],
  )

  const tailTask = tasksChrono.length ? tasksChrono[tasksChrono.length - 1]! : undefined
  const tailTaskId = tailTask?.id
  const lastTaskExecutionFailed =
    Boolean(sessionId) &&
    !busy &&
    tailTask != null &&
    tailTask.status === 'failed' &&
    tailTaskId === latestSessionTaskId
  const lastTaskFailureMessage =
    lastTaskExecutionFailed && latestTaskDetailQuery?.isSuccess
      ? latestTaskDetailQuery.data?.error_message?.trim() || null
      : null

  /** 刷新后内存无 freeze 时，分页拉全量事件重建 Thought/Action（单次 limit 会截断在 delta 里导致缺 tool_call）。 */
  const taskEventsComposerArchiveQuery = useQuery({
    queryKey: ['task', tailTaskId, 'events', 'composer-archive-full'] as const,
    queryFn: () => getAllTaskEvents(tailTaskId!),
    enabled:
      Boolean(sessionId) &&
      Boolean(tailTaskId) &&
      !busy &&
      tailTask != null &&
      tailTask.status !== 'running' &&
      tailTask.status !== 'pending',
    staleTime: 60_000,
  })

  const composerArchiveRounds = useMemo(() => {
    const frozenOk =
      composerStreamFreeze != null &&
      sessionId != null &&
      tailTaskId != null &&
      composerStreamFreeze.sessionId === sessionId &&
      composerStreamFreeze.taskId === tailTaskId
    if (frozenOk) return composerStreamFreeze.rounds
    const ev = taskEventsComposerArchiveQuery.data
    if (!ev?.length) return null
    const { rounds } = foldComposerLlmStreamForFreeze(ev)
    return composerRoundsHaveContent(rounds) ? rounds : null
  }, [composerStreamFreeze, sessionId, tailTaskId, taskEventsComposerArchiveQuery.data])

  const archiveMatchesSessionTask =
    !busy &&
    sessionId != null &&
    tailTaskId != null &&
    composerArchiveRounds != null &&
    composerRoundsHaveContent(composerArchiveRounds)

  const insertArchiveBeforeLastAssistant =
    archiveMatchesSessionTask &&
    messages.length > 0 &&
    messages[messages.length - 1]?.role === 'assistant'

  const showArchiveAfterMessages =
    archiveMatchesSessionTask && !insertArchiveBeforeLastAssistant

  const isStreamingTask = Boolean(busy && pendingTaskId)
  const composerActionDisabled =
    !sessionId ||
    startTaskMutation.isPending ||
    stopTaskMutation.isPending ||
    (!isStreamingTask && !draft.trim())

  /** 底栏上下文环：整会话落库消息 + 草稿 +（生成中）流式块 +（完成后）归档 Thought/Action 粗估 */
  const composerContextUsedTokens = useMemo(() => {
    let n = estimateMessagesContextTokens(messages)
    n += estimateTokensFromText(draft)
    if (busy) {
      n += estimateTokensFromText(streamedLlm.answer)
      n += Math.ceil(composerRoundsPayloadLength(streamedLlm.rounds) / 3)
    } else if (
      composerArchiveRounds != null &&
      composerRoundsHaveContent(composerArchiveRounds)
    ) {
      n += Math.ceil(composerRoundsPayloadLength(composerArchiveRounds) / 3)
    }
    return n
  }, [messages, draft, busy, streamedLlm.answer, streamedLlm.rounds, composerArchiveRounds])

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
   * 返回 `taskId` 供 To-do 进度与 SSE / 归档 / 事件查询对齐。
   */
  const planContextAfterUserMessageAt = useMemo(() => {
    const userMessageCount = messages.filter((x) => x.role === 'user').length
    return (messageIndex: number): { steps: PlanStep[]; taskId: string } | null => {
      const row = messages[messageIndex]
      if (!row || row.role !== 'user') return null
      if (tasksChrono.length === 0) return null
      const userTurn =
        messages.slice(0, messageIndex + 1).filter((x) => x.role === 'user').length - 1
      const isLastUser = messageIndex === lastUserMessageIndex
      let tid: string | undefined
      if (isLastUser) {
        if (busy && pendingTaskId) {
          tid = pendingTaskId
        } else {
          /**
           * 停止并回滚删除本轮用户消息后：tasks 仍含已取消任务，user 气泡少一条，
           * 末尾任务与「最后一条用户气泡」不对齐，应按 userTurn 索引取任务，避免把取消任务挂到上一条用户上。
           */
          const tailOrphanTasks = tasksChrono.length > userMessageCount
          tid = tailOrphanTasks
            ? tasksChrono[userTurn]?.id
            : tasksChrono[tasksChrono.length - 1]?.id
        }
      } else {
        tid = tasksChrono[userTurn]?.id
      }
      if (!tid) return null
      let steps: PlanStep[] | null = null
      if (isLastUser && busy && planForComposer?.length) {
        steps = planForComposer
      } else {
        const archived = plansByTaskId[tid]?.steps
        if (archived?.length) steps = archived
        else {
          const fromServer = planFromServerByTaskId[tid]
          if (fromServer?.length) steps = fromServer
          else if (isLastUser && planForComposer?.length) steps = planForComposer
        }
      }
      if (!steps?.length) return null
      return { steps, taskId: tid }
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

  /** live > 归档终态 todo > GET events 推导；无事件时等价于全部待办。 */
  const resolvePlanTodoProgress = useCallback(
    (taskId: string, steps: PlanStep[]): PlanTodoProgress => {
      if (pendingTaskId === taskId && liveTaskEvents.length > 0) {
        return derivePlanTodoProgress(liveTaskEvents, steps)
      }
      const archivedTodo = plansByTaskId[taskId]?.todoProgress
      if (archivedTodo) return archivedTodo
      const remoteEv = taskEventsByIdForChat[taskId]
      if (remoteEv?.length) {
        return derivePlanTodoProgress(remoteEv, steps)
      }
      return derivePlanTodoProgress([], steps)
    },
    [pendingTaskId, liveTaskEvents, plansByTaskId, taskEventsByIdForChat],
  )

  /** 与原先消息内 To-do 气泡一致：优先 detached（流式尾部），否则对齐最后一条用户消息对应任务 */
  const headerPlanContext = useMemo((): {
    steps: PlanStep[]
    taskId: string
  } | null => {
    if (!sessionId) return null
    if (
      detachedComposerPlan?.sessionId === sessionId &&
      detachedComposerPlan.steps.length > 0
    ) {
      return {
        steps: detachedComposerPlan.steps,
        taskId: detachedComposerPlan.taskId,
      }
    }
    if (lastUserMessageIndex < 0) return null
    return planContextAfterUserMessageAt(lastUserMessageIndex)
  }, [
    sessionId,
    detachedComposerPlan?.sessionId,
    detachedComposerPlan?.taskId,
    detachedComposerPlan?.steps,
    lastUserMessageIndex,
    planContextAfterUserMessageAt,
  ])

  useLayoutEffect(() => {
    if (sessionId !== prevSessionIdForScrollRef.current) {
      prevSessionIdForScrollRef.current = sessionId
      forceScrollToLatestRef.current = true
    }

    const root = messagesScrollRef.current
    const end = listEndRef.current
    if (!end || !sessionId) return

    const force = forceScrollToLatestRef.current
    if (force && messagesQuery.isLoading) {
      return
    }

    if (!force && busy && root && !isNearScrollBottom(root)) {
      return
    }

    end.scrollIntoView({ behavior: 'auto', block: 'end' })
    if (force) {
      forceScrollToLatestRef.current = false
    }
  }, [
    sessionId,
    messagesQuery.isLoading,
    messagesQuery.data?.messages.length,
    busy,
    composerRoundsPayloadLength(streamedLlm.rounds),
    streamedLlm.answer.length,
    composerArchiveRounds ? composerRoundsPayloadLength(composerArchiveRounds) : 0,
  ])

  const sessionLoadError =
    sessionDetailQuery.error &&
    !(sessionDetailQuery.error instanceof ApiRequestError && sessionDetailQuery.error.status === 404)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-2 pt-1 pb-2 sm:px-3 sm:pt-1.5 sm:pb-2.5">
        <div className="mb-1 shrink-0 border-neutral-200/80 border-b bg-white/90 px-2 py-1.5 sm:px-3 sm:py-2">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <div className="flex shrink-0 items-center gap-1.5 self-center">
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
                {sessionId ? (
                  <button
                    type="button"
                    onClick={() => setWorkspaceSidebarOpen((v) => !v)}
                    aria-pressed={workspaceSidebarOpen}
                    aria-label={workspaceSidebarOpen ? '隐藏工作区侧栏' : '显示工作区侧栏'}
                    className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
                  >
                    <ChatHeaderWorkspaceIcon className="size-[1.375rem]" />
                  </button>
                ) : null}
              </div>
              <div className="min-w-0 flex-1 self-center text-center">
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
            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-1">
              {(startTaskMutation.error ||
                stopTaskMutation.error ||
                sessionLoadError ||
                messagesQuery.error ||
                (sseError && !busy) ||
                lastTaskExecutionFailed) && (
                <div className="max-h-[min(40vh,20rem)] shrink-0 space-y-2 overflow-y-auto">
                  {startTaskMutation.error ? (
                    <ErrorAlert
                      message="任务创建失败"
                      detail={errDetail(startTaskMutation.error)}
                    />
                  ) : null}
                  {sseError && !busy ? (
                    <ErrorAlert
                      message="任务进度同步失败"
                      detail={sseError}
                      onDismiss={() => useComposerTaskStore.getState().ackSseError()}
                    />
                  ) : null}
                  {lastTaskExecutionFailed ? (
                    <ErrorAlert
                      key={tailTaskId}
                      message="本轮任务执行失败"
                      detail={
                        lastTaskFailureMessage ??
                        (latestTaskDetailQuery?.isFetching
                          ? '正在加载失败原因…'
                          : '任务未正常结束，请稍后重试或查看任务详情中的事件记录。')
                      }
                    />
                  ) : null}
                  {stopTaskMutation.error ? (
                    <ErrorAlert
                      message="停止任务失败"
                      detail={errDetail(stopTaskMutation.error)}
                    />
                  ) : null}
                  {sessionLoadError ? (
                    <ErrorAlert message="加载会话失败" detail={errDetail(sessionDetailQuery.error)} />
                  ) : null}
                  {messagesQuery.error ? (
                    <ErrorAlert message="加载消息失败" detail={errDetail(messagesQuery.error)} />
                  ) : null}
                </div>
              )}

              <div className="fa-chat-canvas flex min-h-0 flex-1 min-w-0 flex-col md:flex-row">
                <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                  {headerPlanContext ? (
                    <ChatHeaderPlanTodos
                      steps={headerPlanContext.steps}
                      todoProgress={resolvePlanTodoProgress(
                        headerPlanContext.taskId,
                        headerPlanContext.steps,
                      )}
                    />
                  ) : null}
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
                            disabled={
                              busy ||
                              startTaskMutation.isPending ||
                              stopTaskMutation.isPending
                            }
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
                    const archiveBeforeThisAssistant =
                      insertArchiveBeforeLastAssistant &&
                      i === messages.length - 1 &&
                      m.role === 'assistant'
                    return (
                      <Fragment key={m.id}>
                        {archiveBeforeThisAssistant && composerArchiveRounds ? (
                          <ComposerLlmStreamPanel
                            variant="archived"
                            rounds={composerArchiveRounds}
                            answer=""
                            sseError={null}
                          />
                        ) : null}
                        <MessageBubble
                          message={m}
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
                          showStopOnHover={
                            isStreamingTask &&
                            m.role === 'user' &&
                            i === lastUserMessageIndex
                          }
                          stopGenerationPending={stopTaskMutation.isPending}
                          onStopGeneration={() => stopTaskMutation.mutate()}
                          actionsPending={
                            startTaskMutation.isPending || stopTaskMutation.isPending
                          }
                        />
                      </Fragment>
                    )
                  })}
                  {busy ? (
                    <ComposerLlmStreamPanel
                      variant="streaming"
                      rounds={streamedLlm.rounds}
                      answer={streamedLlm.answer}
                      sseError={sseError}
                    />
                  ) : null}
                  {showArchiveAfterMessages && composerArchiveRounds ? (
                    <ComposerLlmStreamPanel
                      variant="archived"
                      rounds={composerArchiveRounds}
                      answer=""
                      sseError={null}
                    />
                  ) : null}
                  <div ref={listEndRef} />
                </div>

                <form onSubmit={handleSubmit} className="fa-chat-composer">
                  <div className="fa-chat-composer-inner">
                    <ComposerContextRing
                      usedTokens={composerContextUsedTokens}
                      windowTokens={LLM_CONTEXT_WINDOW_TOKENS}
                      className="translate-y-[0.5px]"
                    />
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      rows={1}
                      disabled={
                        busy || startTaskMutation.isPending || stopTaskMutation.isPending
                      }
                      className="fa-chat-composer-input"
                    />
                    <button
                      type="button"
                      onClick={() => runComposerPrimaryAction()}
                      disabled={composerActionDisabled}
                      className="fa-chat-composer-submit"
                      aria-label={
                        startTaskMutation.isPending
                          ? '正在启动'
                          : stopTaskMutation.isPending
                            ? '正在停止'
                            : isStreamingTask
                            ? '停止生成'
                            : '发送'
                      }
                    >
                      {startTaskMutation.isPending || stopTaskMutation.isPending ? (
                        <span
                          className="fa-chat-send-spinner fa-chat-send-spinner--sm"
                          aria-hidden
                        />
                      ) : isStreamingTask ? (
                        <ChatStopIcon className="size-4" />
                      ) : (
                        <ChatSendArrowIcon className="size-4" />
                      )}
                    </button>
                  </div>
                </form>
                </div>
                {workspaceSidebarOpen ? <ChatWorkspaceSidebar /> : null}
              </div>
            </div>
          )}
      </div>
    </div>
  )
}

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
