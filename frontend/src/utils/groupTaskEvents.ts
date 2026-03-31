/**
 * 将任务事件按 step_id 分组，便于时间线以「一步 / 一轮工具」展示。
 */

import type { TaskEvent } from '@/types/task'

/** 时间线渲染单元：单条事件，或同一执行步骤的一组事件。 */
export type TimelineRenderable =
  | { type: 'single'; event: TaskEvent }
  | { type: 'step_group'; stepId: string; events: TaskEvent[] }

function stepIdFromPayload(payload: Record<string, unknown> | null): string | null {
  if (!payload) return null
  const raw = payload.step_id
  if (raw === undefined || raw === null) return null
  return String(raw)
}

/**
 * 将事件按 seq 排序后，把共享同一 step_id 且以 step_start 开头的片段合并为 step_group。
 */
export function buildTimelineRenderables(events: TaskEvent[]): TimelineRenderable[] {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const out: TimelineRenderable[] = []
  let i = 0
  while (i < sorted.length) {
    const ev = sorted[i]
    if (ev.kind === 'step_start') {
      const sid = stepIdFromPayload(ev.payload)
      if (sid) {
        const group: TaskEvent[] = [ev]
        i += 1
        while (i < sorted.length) {
          const next = sorted[i]
          const nid = stepIdFromPayload(next.payload)
          if (nid === sid) {
            group.push(next)
            i += 1
            if (next.kind === 'step_end') break
          } else if (nid === null && next.kind === 'llm_stream_delta') {
            // 兼容旧数据：ReAct 流式增量曾不带 step_id，会打断分组导致卡片误显「进行中 / 未调用工具」
            group.push(next)
            i += 1
          } else {
            break
          }
        }
        out.push({ type: 'step_group', stepId: sid, events: group })
        continue
      }
    }
    out.push({ type: 'single', event: ev })
    i += 1
  }
  return out
}
