import type { TaskEvent } from '@/types/task'

/**
 * 聚合 llm_stream_delta。
 * 默认只统计「最后一次 step_start」之后的事件，便于 ReAct 多轮时对话区只展示当前回合的流式思考/行动/答复。
 */
export function foldLlmStreamDeltas(
  events: TaskEvent[],
  options?: { onlySinceLastStepStart?: boolean },
): {
  thinking: string
  action: string
  answer: string
} {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const sinceLast = options?.onlySinceLastStepStart !== false
  let slice = sorted
  if (sinceLast) {
    let cut = 0
    for (let i = sorted.length - 1; i >= 0; i--) {
      if (sorted[i]!.kind === 'step_start') {
        cut = i + 1
        break
      }
    }
    slice = sorted.slice(cut)
  }

  let thinking = ''
  let action = ''
  let answer = ''
  for (const e of slice) {
    if (e.kind !== 'llm_stream_delta' || !e.payload) continue
    const phase = e.payload.phase
    const delta = e.payload.delta
    if (phase === 'thinking' && typeof delta === 'string') thinking += delta
    if (phase === 'action' && typeof delta === 'string') action += delta
    if (phase === 'answer' && typeof delta === 'string') answer += delta
  }
  return { thinking, action, answer }
}
