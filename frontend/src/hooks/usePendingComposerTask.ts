/**
 * 对话 composer 与执行任务绑定：REST 拉全量事件 + SSE 增量，写入 composerTaskStore；
 * ChatPage 只消费 liveTaskEvents / busy 状态，与具体传输层解耦。
 */
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { buildTaskEventsStreamUrl, consumeTaskEventStream } from '@/api/sse'
import { getTaskEvents } from '@/api/tasks'
import { useComposerTaskStore } from '@/store/composerTaskStore'
import type { TaskEvent } from '@/types/task'

const EVENT_PAGE_LIMIT = 200

function isAbortError(e: unknown): boolean {
  if (e instanceof DOMException && e.name === 'AbortError') return true
  return e instanceof Error && e.name === 'AbortError'
}

function sortEventsFromMap(bySeq: Map<number, TaskEvent>): TaskEvent[] {
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
}

function maxSeqInMap(bySeq: Map<number, TaskEvent>): number {
  let m = 0
  for (const e of bySeq.values()) {
    if (e.seq > m) m = e.seq
  }
  return m
}

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

    async function run() {
      store.setSsePhase('loading')
      store.setSseError(null)
      const bySeq = new Map<number, TaskEvent>()

      try {
        let cursor: number | undefined = undefined
        while (!cancelled) {
          const res = await getTaskEvents(taskId, cursor, EVENT_PAGE_LIMIT)
          if (cancelled) return
          for (const e of res.events) {
            bySeq.set(e.seq, e)
            if (e.kind === 'llm_stream_delta') {
              useComposerTaskStore.setState({ lastComposerHadLlmStream: true })
            }
          }
          if (res.events.length < EVENT_PAGE_LIMIT) break
          cursor = res.events[res.events.length - 1]!.seq
        }

        useComposerTaskStore.getState().setLiveEvents(sortEventsFromMap(bySeq))
        if (cancelled) return

        useComposerTaskStore.getState().setSsePhase('streaming')
        const startAfter = maxSeqInMap(bySeq)
        const streamUrl = buildTaskEventsStreamUrl(taskId, startAfter)
        await consumeTaskEventStream(streamUrl, ac.signal, (e) => {
          if (cancelled) return
          if (e.kind === 'llm_stream_delta') {
            useComposerTaskStore.setState({ lastComposerHadLlmStream: true })
          }
          bySeq.set(e.seq, e)
          useComposerTaskStore.getState().setLiveEvents(sortEventsFromMap(bySeq))
          if (
            e.kind === 'plan_created' ||
            e.kind === 'replan' ||
            e.kind === 'error'
          ) {
            void queryClient.invalidateQueries({ queryKey: ['task', taskId] })
          }
        })

        if (cancelled) return

        const lastSeq = maxSeqInMap(bySeq)
        const gap = await getTaskEvents(taskId, lastSeq, EVENT_PAGE_LIMIT)
        if (!cancelled && gap.events.length > 0) {
          for (const e of gap.events) {
            bySeq.set(e.seq, e)
            if (e.kind === 'llm_stream_delta') {
              useComposerTaskStore.setState({ lastComposerHadLlmStream: true })
            }
          }
          useComposerTaskStore.getState().setLiveEvents(sortEventsFromMap(bySeq))
        }

        await queryClient.invalidateQueries({ queryKey: ['task', taskId] })
        if (sessionId) {
          await queryClient.refetchQueries({
            queryKey: ['session', sessionId, 'messages'],
          })
        }
        await queryClient.invalidateQueries({ queryKey: ['tasks'] })
        if (!cancelled) {
          useComposerTaskStore.getState().setSsePhase('idle')
          useComposerTaskStore.getState().clearPending()
        }
      } catch (e) {
        if (cancelled || isAbortError(e)) return
        useComposerTaskStore.getState().setSsePhase('error')
        useComposerTaskStore.getState().setSseError(
          e instanceof Error ? e.message : 'SSE 异常',
        )
        if (sessionId) {
          void queryClient.invalidateQueries({
            queryKey: ['session', sessionId, 'messages'],
          })
        }
        void queryClient.invalidateQueries({ queryKey: ['tasks'] })
        useComposerTaskStore.getState().clearPending()
      }
    }

    void run()
    return () => {
      cancelled = true
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
