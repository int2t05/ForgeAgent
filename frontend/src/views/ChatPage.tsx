/**
 * 对话页
 *
 * - 会话列表在全局 Sidebar 主导航下方
 * - 与 PRD 一致的四块能力在 UI 上的体现——记忆（消息列表）、规划（plan 气泡）、执行（任务流 + SSE 流式块）、归因到会话的任务入口
 * - 样式：`index.css` 中 `fa-chat-*`，正文宽度随主区域铺满
 */

import {
  Fragment,
  useCallback,
  useEffect,
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
import { resolvePlanStepsAfterComposerStop } from '@/utils/resolvePlanStepsAfterComposerStop'
import { ChatHeaderPlanTodos } from '@/components/chat/ChatHeaderPlanTodos'
import { ChatPageHeaderBar } from '@/components/chat/ChatPageHeaderBar'
import { ChatSendArrowIcon, ChatStopIcon } from '@/components/chat/ChatPageIcons'
import { MessageBubble } from '@/components/chat/ChatMessageBubble'
import { ChatWorkspaceSidebar } from '@/components/chat/ChatWorkspaceSidebar'
import { ComposerContextRing } from '@/components/chat/ComposerContextRing'
import { ComposerLlmStreamPanel } from '@/components/chat/ComposerLlmStreamPanel'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { useMainNavSidebarStore } from '@/store/mainNavSidebarStore'
import { useChatPageMessagesScroll } from '@/hooks/useChatPageMessagesScroll'
import { useSession } from '@/hooks/useSession'
import { useWorkspaceSidebarOpen } from '@/hooks/useWorkspaceSidebarOpen'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
} from '@/hooks/usePendingComposerTask'
import { useTaskCompletionNotification } from '@/hooks/useTaskCompletionNotification'
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
import { CHAT_STARTER_PROMPTS } from '@/constants/chatStarters'
import { TERMINAL_STATUSES } from '@/constants/task'
import type { Message } from '@/types/session'
import type { TaskDetail, TaskEvent } from '@/types/task'

export function ChatPage() {
  const queryClient = useQueryClient()
  const { sessionId, setSessionId, clearSession } = useSession()
  const mainNavOpen = useMainNavSidebarStore((s) => s.open)
  const toggleMainNav = useMainNavSidebarStore((s) => s.toggle)
  const [draft, setDraft] = useState('')
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const prevBusyRef = useRef(false)
  /** 发送或从服务端恢复进行中任务时记下会话：clearPending 后仅靠 store 无法判断是否本轮对话。 */
  const composerTargetSessionRef = useRef<string | null>(null)

  const [workspaceSidebarOpen, setWorkspaceSidebarOpen] = useWorkspaceSidebarOpen()

  useTaskCompletionNotification()

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
   * busy 时也保留 sticky 作为 fallback，避免新任务开始瞬间刷掉上一轮步骤。
   */
  const planForComposer = useMemo(() => {
    if (!sessionId) return null
    const fromLive = latestPlanStepsFromEvents(liveTaskEvents)
    if (fromLive?.length) return fromLive
    const sticky = stickyPlansBySession[sessionId]
    if (sticky?.length) return sticky
    if (busy) return null
    return persistedPlanSteps
  }, [sessionId, liveTaskEvents, stickyPlansBySession, busy, persistedPlanSteps])

  /** 规划气泡插在最后一条用户消息之后（用户 → 规划 → 助手），与会话时间线一致。 */
  const lastUserMessageIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]!.role === 'user') return i
    }
    return -1
  }, [messages])

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

  /**
   * 顶栏 To-do：优先 detached（停止回滚后暂挂规划）；否则对齐「当前最新任务」——
   * 执行中用 pending，空闲用会话任务列表按创建时间最后一条（与 tailTaskId 一致），
   * 不再按最后一条用户气泡索引对齐，避免多任务 / 删消息时仍显示旧任务步骤。
   */
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
    const tid = busy && pendingTaskId ? pendingTaskId : tailTaskId
    if (!tid) return null
    let steps: PlanStep[] | null = null
    if (busy && pendingTaskId === tid && planForComposer?.length) {
      steps = planForComposer
    } else {
      const archived = plansByTaskId[tid]?.steps
      if (archived?.length) steps = archived
      else {
        const fromServer = planFromServerByTaskId[tid]
        if (fromServer?.length) steps = fromServer
        else if (busy && pendingTaskId === tid && planForComposer?.length) steps = planForComposer
      }
    }
    if (!steps?.length) return null
    return { steps, taskId: tid }
  }, [
    sessionId,
    detachedComposerPlan?.sessionId,
    detachedComposerPlan?.taskId,
    detachedComposerPlan?.steps,
    busy,
    pendingTaskId,
    tailTaskId,
    planForComposer,
    plansByTaskId,
    planFromServerByTaskId,
  ])

  const streamedRoundsPayloadLen = composerRoundsPayloadLength(streamedLlm.rounds)
  const archiveRoundsPayloadLen = composerArchiveRounds
    ? composerRoundsPayloadLength(composerArchiveRounds)
    : 0
  const { messagesScrollRef, listEndRef } = useChatPageMessagesScroll({
    sessionId,
    messagesLoading: messagesQuery.isLoading,
    messagesLen: messagesQuery.data?.messages.length ?? 0,
    busy,
    streamedRoundsPayloadLen,
    streamedAnswerLen: streamedLlm.answer.length,
    archiveRoundsPayloadLen,
  })

  const sessionLoadError =
    sessionDetailQuery.error &&
    !(sessionDetailQuery.error instanceof ApiRequestError && sessionDetailQuery.error.status === 404)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-2 pt-1 pb-2 sm:px-3 sm:pt-1.5 sm:pb-2.5">
        <ChatPageHeaderBar
          mainNavOpen={mainNavOpen}
          onToggleMainNav={toggleMainNav}
          onNewSession={() => createSessionHeaderMutation.mutate()}
          newSessionPending={createSessionHeaderMutation.isPending}
          sessionId={sessionId}
          workspaceSidebarOpen={workspaceSidebarOpen}
          onToggleWorkspaceSidebar={() => setWorkspaceSidebarOpen((v) => !v)}
          sessionTitle={sessionDetailQuery.data?.title}
        />

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
