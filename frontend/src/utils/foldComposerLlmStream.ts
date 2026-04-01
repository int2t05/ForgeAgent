import type { TaskEvent } from '@/types/task'
import { foldLlmStreamDeltasSorted } from '@/utils/foldLlmStreamDeltas'
import { splitThinkingFromMessage } from '@/utils/parseMessageThinking'
import { peelLeadingThinkBlockFromBuffer } from '@/utils/streamThinkAnswer'

/** 单轮 Action 折叠块 */
export interface ComposerActionBlock {
  id: string
  subtitle?: string
  body: string
}

/** 按 ReAct / 执行步顺序：一轮 Thought 紧跟一轮 Action（可无） */
export interface ComposerRoundSegment {
  id: string
  roundIndex: number
  thought: string
  action: ComposerActionBlock | null
}

export function composerRoundsHaveContent(rounds: ComposerRoundSegment[]): boolean {
  return rounds.some((r) => r.thought.trim().length > 0 || r.action != null)
}

export function composerRoundsPayloadLength(rounds: ComposerRoundSegment[]): number {
  return rounds.reduce((n, r) => n + r.thought.length + (r.action?.body.length ?? 0), 0)
}

function formatToolCallPayload(payload: Record<string, unknown> | null): string {
  if (!payload) return ''
  const tool = payload.tool
  const args = payload.args
  if (typeof tool !== 'string' || !tool.trim()) return ''
  const argsObj =
    args && typeof args === 'object' && !Array.isArray(args)
      ? (args as Record<string, unknown>)
      : {}
  try {
    return `调用工具：${tool}\n${JSON.stringify(argsObj, null, 2)}`
  } catch {
    return `调用工具：${tool}`
  }
}

function toolEventToBlock(e: TaskEvent): ComposerActionBlock | null {
  if (e.kind !== 'tool_call' || !e.payload || typeof e.payload !== 'object') return null
  const p = e.payload as Record<string, unknown>
  const tool = typeof p.tool === 'string' ? p.tool.trim() : ''
  const body = formatToolCallPayload(p)
  if (!body) return null
  return { id: `tool-${e.seq}`, subtitle: tool || undefined, body }
}

/** 落在 (afterSeq, untilSeq] 内的 llm_stream_delta（untilSeq 可极大） */
function foldLlmStreamDeltasInSeqRange(
  sorted: TaskEvent[],
  afterSeq: number,
  untilSeq: number,
): { thinking: string; action: string; answer: string } {
  let thinking = ''
  let action = ''
  let answer = ''
  for (const e of sorted) {
    if (e.seq <= afterSeq) continue
    if (e.seq > untilSeq) break
    if (e.kind !== 'llm_stream_delta' || !e.payload) continue
    const phase = e.payload.phase
    const delta = e.payload.delta
    if (phase === 'thinking' && typeof delta === 'string') thinking += delta
    if (phase === 'action' && typeof delta === 'string') action += delta
    if (phase === 'answer' && typeof delta === 'string') answer += delta
  }
  return { thinking, action, answer }
}

/** 最后一次 step_start 之后最近的 tool_call（events 需已按 seq 升序） */
function lastToolCallActionSinceLastStepSorted(sorted: TaskEvent[]): string {
  let cut = 0
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (sorted[i]!.kind === 'step_start') {
      cut = i + 1
      break
    }
  }
  let last = ''
  for (let i = cut; i < sorted.length; i++) {
    const e = sorted[i]!
    if (e.kind !== 'tool_call' || !e.payload || typeof e.payload !== 'object') continue
    const f = formatToolCallPayload(e.payload as Record<string, unknown>)
    if (f) last = f
  }
  return last
}

function collapseWs(s: string): string {
  return s.replace(/\s+/g, ' ').trim()
}

/**
 * 合并两段思考展示文本：整段相同（忽略空白折行）或一段为另一段子串时不重复拼接，
 * 避免 step_start.thought 与 llm_stream_delta thinking / 标签内思考各写一份导致「———」隔开的双段重复。
 */
function joinThoughtPair(a: string, b: string): string {
  const x = a.trim()
  const y = b.trim()
  if (!x) return y
  if (!y) return x
  if (collapseWs(x) === collapseWs(y)) return x.length >= y.length ? x : y
  if (y.includes(x) && x.length > 0) return y
  if (x.includes(y) && y.length > 0) return x
  return `${x}\n\n———\n\n${y}`
}

function mergeThoughtDisplayParts(...parts: string[]): string {
  let acc = ''
  for (const p of parts) {
    const t = p.trim()
    if (!t) continue
    acc = acc === '' ? t : joinThoughtPair(acc, t)
  }
  return acc
}

function lastCommittedThoughtFromStepStartsSorted(sorted: TaskEvent[]): string {
  let last = ''
  for (const e of sorted) {
    if (e.kind !== 'step_start' || !e.payload) continue
    const th = e.payload.thought
    if (typeof th === 'string' && th.trim()) last = th.trim()
  }
  return last
}

function mergeAnswerThinkIntoDisplayThinking(
  streamThinking: string,
  answerRaw: string,
): { thinking: string; answer: string } {
  const { think: xmlThink, visible: afterXml } = peelLeadingThinkBlockFromBuffer(answerRaw)
  const rest = splitThinkingFromMessage(afterXml)
  const fromTags = mergeThoughtDisplayParts(xmlThink, rest.thinking ?? '')
  const thinking = mergeThoughtDisplayParts(streamThinking, fromTags)
  return { thinking: thinking.trim(), answer: rest.body }
}

/**
 * 对话 Composer：当前窗口内的流式折叠（仍用「最后一轮」切片，供底部 answer 等使用）。
 * @param sorted 已按 seq 升序排列的事件
 */
function foldComposerLlmStreamSorted(sorted: TaskEvent[]): {
  thinking: string
  action: string
  answer: string
} {
  const folded = foldLlmStreamDeltasSorted(sorted, { onlySinceLastStepStart: true })
  const merged = mergeAnswerThinkIntoDisplayThinking(folded.thinking, folded.answer)
  const stepFall = lastCommittedThoughtFromStepStartsSorted(sorted)
  const thinking = merged.thinking || stepFall
  const streamAction = folded.action
  const fromTool = lastToolCallActionSinceLastStepSorted(sorted)
  const action = streamAction || fromTool
  return {
    thinking,
    action,
    answer: merged.answer,
  }
}

export function foldComposerLlmStream(events: TaskEvent[]): {
  thinking: string
  action: string
  answer: string
} {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  return foldComposerLlmStreamSorted(sorted)
}

/**
 * 按 step_start 分段：每段 Thought → Action 交替；有几段思考就展示几个 Thought，其后跟该轮 Action。
 */
function buildComposerRoundSegmentsSorted(
  sorted: TaskEvent[],
  busy: boolean,
): ComposerRoundSegment[] {
  const stepStarts = sorted.filter((e) => e.kind === 'step_start')
  const maxSeq = Number.MAX_SAFE_INTEGER

  if (stepStarts.length === 0) {
    const stream = foldLlmStreamDeltasInSeqRange(sorted, 0, maxSeq)
    const merged = mergeAnswerThinkIntoDisplayThinking(stream.thinking, stream.answer)
    const thought = merged.thinking.trim()
    const tools = sorted.filter((e) => e.kind === 'tool_call')
    const lastTool = tools[tools.length - 1]
    let action: ComposerActionBlock | null = lastTool ? toolEventToBlock(lastTool) : null
    if (!action && stream.action.trim()) {
      action = {
        id: 'stream-0',
        subtitle: busy ? '进行中' : '流式',
        body: stream.action,
      }
    }
    if (!thought && !action) return []
    return [{ id: 'r1', roundIndex: 1, thought, action }]
  }

  const out: ComposerRoundSegment[] = []
  for (let i = 0; i < stepStarts.length; i++) {
    const ss = stepStarts[i]!
    const nextSeq = stepStarts[i + 1]?.seq ?? maxSeq
    const stream = foldLlmStreamDeltasInSeqRange(sorted, ss.seq, nextSeq)
    const merged = mergeAnswerThinkIntoDisplayThinking(stream.thinking, stream.answer)
    const rawThought =
      typeof ss.payload?.thought === 'string' ? ss.payload.thought.trim() : ''
    const thought = mergeThoughtDisplayParts(rawThought, merged.thinking).trim()

    const toolsInRange = sorted.filter(
      (e) => e.kind === 'tool_call' && e.seq > ss.seq && e.seq <= nextSeq,
    )
    const lastTool = toolsInRange[toolsInRange.length - 1]
    let action: ComposerActionBlock | null = null
    if (lastTool) {
      action = toolEventToBlock(lastTool)
    } else if (stream.action.trim()) {
      action = {
        id: `stream-${ss.seq}`,
        subtitle: busy ? '进行中' : '流式',
        body: stream.action,
      }
    }

    const sid =
      typeof ss.payload?.step_id === 'string' && ss.payload.step_id.trim()
        ? ss.payload.step_id
        : `step-${ss.seq}`

    out.push({
      id: sid,
      roundIndex: i + 1,
      thought,
      action,
    })
  }
  return out
}

export function buildComposerRoundSegments(
  events: TaskEvent[],
  busy: boolean,
): ComposerRoundSegment[] {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  return buildComposerRoundSegmentsSorted(sorted, busy)
}

export function foldComposerLlmStreamForBusy(events: TaskEvent[], busy: boolean): {
  thinking: string
  action: string
  answer: string
  rounds: ComposerRoundSegment[]
} {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const folded = foldComposerLlmStreamSorted(sorted)
  return {
    ...folded,
    rounds: buildComposerRoundSegmentsSorted(sorted, busy),
  }
}

export function foldComposerLlmStreamForFreeze(events: TaskEvent[]): {
  rounds: ComposerRoundSegment[]
} {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  return { rounds: buildComposerRoundSegmentsSorted(sorted, false) }
}
