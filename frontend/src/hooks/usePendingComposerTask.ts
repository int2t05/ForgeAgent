/**
 * 对话 composer 与执行任务绑定：REST 拉全量事件 + SSE 增量，写入 composerTaskStore；
 * ChatPage 只消费 liveTaskEvents / busy 状态，与具体传输层解耦。
 */
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { buildTaskEventsStreamUrl, consumeTaskEventStream } from '@/api/sse'
import { getAllTaskEvents, getTask } from '@/api/tasks'
import { useComposerTaskStore } from '@/store/composerTaskStore'
import type { TaskEvent } from '@/types/task'

function isAbortError(e: unknown): boolean {
  if (e instanceof DOMException && e.name === 'AbortError') return true
  return e instanceof Error && e.name === 'AbortError'
}

function sortEventsFromMap(bySeq: Map<number, TaskEvent>): TaskEvent[] {
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
}

/** 在 seq 大体单调递增的 SSE 场景下避免每条事件都全量排序 */
function appendOrResortEvents(
  bySeq: Map<number, TaskEvent>,
  sortedLive: TaskEvent[],
  e: TaskEvent,
): TaskEvent[] {
  const had = bySeq.has(e.seq)
  bySeq.set(e.seq, e)
  if (had) return sortEventsFromMap(bySeq)
  const tail = sortedLive[sortedLive.length - 1]
  if (sortedLive.length === 0 || e.seq > tail!.seq) {
    return [...sortedLive, e]
  }
  return sortEventsFromMap(bySeq)
}

function markLlmStreamIfDelta(e: TaskEvent): void {
  if (e.kind !== 'llm_stream_delta') return
  useComposerTaskStore.setState({ lastComposerHadLlmStream: true })
}

function maxSeqInMap(bySeq: Map<number, TaskEvent>): number {
  let m = 0
  for (const e of bySeq.values()) {
    if (e.seq > m) m = e.seq
  }
  return m
}

const TERMINAL_TASK_STATUSES = new Set(['success', 'failed', 'cancelled'])

function isTerminalTaskStatus(status: string): boolean {
  return TERMINAL_TASK_STATUSES.has(status)
}

const MESSAGE_REFETCH_TIMEOUT_MS = 12_000

export function usePendingComposerTaskSync() {
  const queryClient = useQueryClient()
  const pendingTaskId = useComposerTaskStore((s) => s.pendingTaskId)
  const pendingSessionId = useComposerTaskStore((s) => s.pendingSessionId)

  useEffect(() => {
    const store = useComposerTaskStore.getState()
    if (!pendingTaskId) {
      store.resetLiveOnly()
      return
    }

    const taskId = pendingTaskId
    const sessionId = pendingSessionId
    const ac = new AbortController()
    let cancelled = false
    let rafId = 0
    let abortedForTerminal = false
    let pollTimer: ReturnType<typeof setInterval> | null = null

    async function run() {
      store.setSsePhase('loading')
      store.setSseError(null)
      const bySeq = new Map<number, TaskEvent>()
      let sortedLive: TaskEvent[] = []

      const flushLive = () => {
        if (rafId) {
          cancelAnimationFrame(rafId)
          rafId = 0
        }
        useComposerTaskStore.getState().setLiveEvents(sortedLive)
      }

      const scheduleLive = () => {
        if (rafId) return
        rafId = requestAnimationFrame(() => {
          rafId = 0
          useComposerTaskStore.getState().setLiveEvents(sortedLive)
        })
      }

      try {
        const initial = await getAllTaskEvents(taskId)
        if (cancelled) return
        for (const e of initial) {
          bySeq.set(e.seq, e)
        }
        if (initial.some((e) => e.kind === 'llm_stream_delta')) {
          useComposerTaskStore.setState({ lastComposerHadLlmStream: true })
        }

        sortedLive = sortEventsFromMap(bySeq)
        useComposerTaskStore.getState().setLiveEvents(sortedLive)
        if (cancelled) return

        useComposerTaskStore.getState().setSsePhase('streaming')
        const startAfter = maxSeqInMap(bySeq)
        const streamUrl = buildTaskEventsStreamUrl(taskId, startAfter)

        pollTimer = setInterval(() => {
          void (async () => {
            try {
              const t = await getTask(taskId)
              if (cancelled || abortedForTerminal) return
              if (!isTerminalTaskStatus(t.status)) return
              abortedForTerminal = true
              ac.abort()
            } catch {
              /* 单次轮询失败忽略 */
            }
          })()
        }, 400)

        try {
          await consumeTaskEventStream(streamUrl, ac.signal, (e) => {
            if (cancelled) return
            markLlmStreamIfDelta(e)
            sortedLive = appendOrResortEvents(bySeq, sortedLive, e)
            scheduleLive()
            if (
              e.kind === 'plan_created' ||
              e.kind === 'replan' ||
              e.kind === 'error'
            ) {
              void queryClient.invalidateQueries({ queryKey: ['task', taskId] })
            }
          })
        } finally {
          if (pollTimer != null) {
            clearInterval(pollTimer)
            pollTimer = null
          }
        }

        if (cancelled) return

        flushLive()

        await queryClient.invalidateQueries({ queryKey: ['task', taskId] })
        if (sessionId) {
          await Promise.race([
            queryClient.refetchQueries({
              queryKey: ['session', sessionId, 'messages'],
            }),
            new Promise<void>((resolveMessageRefetch) =>
              setTimeout(resolveMessageRefetch, MESSAGE_REFETCH_TIMEOUT_MS),
            ),
          ])
        }
        await queryClient.invalidateQueries({ queryKey: ['tasks'] })
        if (!cancelled) {
          useComposerTaskStore.getState().setSsePhase('idle')
          useComposerTaskStore.getState().clearPending()
        }
      } catch (e) {
        if (pollTimer != null) {
          clearInterval(pollTimer)
          pollTimer = null
        }
        if (cancelled) return
        if (isAbortError(e) && abortedForTerminal) {
          flushLive()
          await queryClient.invalidateQueries({ queryKey: ['task', taskId] })
          if (sessionId) {
            await Promise.race([
              queryClient.refetchQueries({
                queryKey: ['session', sessionId, 'messages'],
              }),
              new Promise<void>((resolveMessageRefetch) =>
                setTimeout(resolveMessageRefetch, MESSAGE_REFETCH_TIMEOUT_MS),
              ),
            ])
          }
          await queryClient.invalidateQueries({ queryKey: ['tasks'] })
          if (!cancelled) {
            useComposerTaskStore.getState().setSsePhase('idle')
            useComposerTaskStore.getState().clearPending()
          }
          return
        }
        if (isAbortError(e)) return
        useComposerTaskStore.getState().setSsePhase('error')
        useComposerTaskStore.getState().setSseError(
          e instanceof Error ? e.message : '接收任务事件失败',
        )
        if (sessionId) {
          void queryClient.invalidateQueries({
            queryKey: ['session', sessionId, 'messages'],
          })
        }
        void queryClient.invalidateQueries({ queryKey: ['tasks'] })
        useComposerTaskStore.getState().clearPending({ keepSseError: true })
      }
    }

    void run()
    return () => {
      cancelled = true
      if (pollTimer != null) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      if (rafId) cancelAnimationFrame(rafId)
      ac.abort()
    }
  }, [pendingTaskId, pendingSessionId, queryClient])
}

export function usePendingComposerTaskBusy(): boolean {
  return Boolean(useComposerTaskStore((s) => s.pendingTaskId))
}

export function usePendingComposerTaskMeta() {
  const pendingTaskId = useComposerTaskStore((s) => s.pendingTaskId)
  const pendingSessionId = useComposerTaskStore((s) => s.pendingSessionId)
  return { pendingTaskId, pendingSessionId }
}
