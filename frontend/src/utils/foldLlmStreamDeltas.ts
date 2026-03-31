import type { TaskEvent } from '@/types/task'

export function foldLlmStreamDeltas(events: TaskEvent[]): {
  thinking: string
  answer: string
} {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  let thinking = ''
  let answer = ''
  for (const e of sorted) {
    if (e.kind !== 'llm_stream_delta' || !e.payload) continue
    const phase = e.payload.phase
    const delta = e.payload.delta
    if (phase === 'thinking' && typeof delta === 'string') thinking += delta
    if (phase === 'answer' && typeof delta === 'string') answer += delta
  }
  return { thinking, answer }
}
