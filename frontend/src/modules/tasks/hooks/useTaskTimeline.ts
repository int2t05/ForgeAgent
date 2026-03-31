/**
 * 任务可观测时间线：REST 分页补历史 + SSE 增量合并 + 断流后 after_seq 补拉（阶段7）。
 */

import { useQueryClient } from '@tanstack/react-query'
import { startTransition, useEffect, useRef, useState } from 'react'
import { buildTaskEventsStreamUrl, consumeTaskEventStream } from '@/modules/tasks/api/sse'
import { getTaskEvents } from '@/modules/tasks/api/tasks'
import type { TaskEvent } from '@/modules/tasks/types/task'

/** SSE 连接阶段，供 UI 展示。 */
export type TimelineConnectionState =
  | 'idle'
  | 'bootstrapping'
  | 'streaming'
  | 'closed'
  | 'error'

const EVENT_PAGE_LIMIT = 200

function isAbortError(e: unknown): boolean {
  if (e instanceof DOMException && e.name === 'AbortError') {
    return true
  }
  return e instanceof Error && e.name === 'AbortError'
}

function sortEventsFromMap(bySeq: Map<number, TaskEvent>): TaskEvent[] {
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
}

function maxSeqInMap(bySeq: Map<number, TaskEvent>): number {
  let m = 0
  for (const e of bySeq.values()) {
    if (e.seq > m) {
      m = e.seq
    }
  }
  return m
}

/**
 * 拉取某任务的完整事件历史（分页）并订阅 SSE；按 seq 去重合并。
 */
export function useTaskTimeline(taskId: string | undefined) {
  const queryClient = useQueryClient()
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [connectionState, setConnectionState] = useState<TimelineConnectionState>('idle')
  const [loadError, setLoadError] = useState<string | null>(null)
  const bySeqRef = useRef<Map<number, TaskEvent>>(new Map())

  useEffect(() => {
    if (!taskId) {
      bySeqRef.current = new Map()
      startTransition(() => {
        setEvents([])
        setConnectionState('idle')
        setLoadError(null)
      })
      return
    }

    const id = taskId
    let cancelled = false
    const ac = new AbortController()
    bySeqRef.current = new Map()

    async function run() {
      setLoadError(null)
      setConnectionState('bootstrapping')
      try {
        let cursor: number | undefined = undefined
        while (!cancelled) {
          const res = await getTaskEvents(id, cursor, EVENT_PAGE_LIMIT)
          if (cancelled) {
            return
          }
          for (const e of res.events) {
            bySeqRef.current.set(e.seq, e)
          }
          if (res.events.length < EVENT_PAGE_LIMIT) {
            break
          }
          cursor = res.events[res.events.length - 1]!.seq
        }

        const initial = sortEventsFromMap(bySeqRef.current)
        setEvents(initial)

        if (cancelled) {
          return
        }

        setConnectionState('streaming')
        const startAfter = maxSeqInMap(bySeqRef.current)
        const streamUrl = buildTaskEventsStreamUrl(id, startAfter)
        await consumeTaskEventStream(streamUrl, ac.signal, (e) => {
          if (cancelled) {
            return
          }
          bySeqRef.current.set(e.seq, e)
          setEvents(sortEventsFromMap(bySeqRef.current))
          if (e.kind === 'plan_created' || e.kind === 'replan' || e.kind === 'error') {
            void queryClient.invalidateQueries({ queryKey: ['task', id] })
          }
        })

        if (cancelled) {
          return
        }

        const lastSeq = maxSeqInMap(bySeqRef.current)
        const gap = await getTaskEvents(id, lastSeq, EVENT_PAGE_LIMIT)
        if (!cancelled && gap.events.length > 0) {
          for (const e of gap.events) {
            bySeqRef.current.set(e.seq, e)
          }
          setEvents(sortEventsFromMap(bySeqRef.current))
        }

        await queryClient.invalidateQueries({ queryKey: ['task', id] })
        if (!cancelled) {
          setConnectionState('closed')
        }
      } catch (e) {
        if (cancelled || isAbortError(e)) {
          return
        }
        setLoadError(e instanceof Error ? e.message : '时间线加载失败')
        setConnectionState('error')
      }
    }

    void run()
    return () => {
      cancelled = true
      ac.abort()
    }
  }, [taskId, queryClient])

  return { events, connectionState, loadError }
}
