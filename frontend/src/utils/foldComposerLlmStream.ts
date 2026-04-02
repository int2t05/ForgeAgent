import type { TaskEvent } from '@/types/task'
import { foldLlmStreamDeltasSorted } from '@/utils/foldLlmStreamDeltas'
import { splitThinkingFromMessage } from '@/utils/parseMessageThinking'
import { peelLeadingThinkBlockFromBuffer } from '@/utils/streamThinkAnswer'

/**
 * 最后一轮「规划边界」序号：之后的执行/流式事件才属于当前计划周期。
 * 避免重规划后仍以全局最后一个 step_start 切片，把上一轮已输出的 answer 误切掉或与新步混淆。
 */
export function planCycleAnchorSeq(sorted: TaskEvent[]): number {
  let a = 0
  for (const e of sorted) {
    if (e.kind === 'replan' || e.kind === 'plan_created') {
      if (e.seq > a) a = e.seq
    }
  }
  return a
}

/** 只保留当前规划周期内事件（供对话区流式与轮次折叠）。 */
export function sliceTaskEventsForActivePlanCycle(sorted: TaskEvent[]): TaskEvent[] {
  const anchor = planCycleAnchorSeq(sorted)
  if (anchor === 0) return sorted
  return sorted.filter((e) => e.seq > anchor)
}

/** 单轮 Action 折叠块 */
export interface ComposerToolActionPanel {
  id: string
  /** 小节标题（plain 或 code 非折叠时用作说明） */
  title?: string
  variant: 'plain' | 'code'
  content: string
  /** 若设置，在面板旁展示复制按钮（如绝对路径） */
  copyText?: string
  /**
   * code：套在 details 内且默认收起（read 结果、shell 输出）。
   */
  collapsible?: boolean
  /**
   * code 且非 collapsible：默认只显示前 N 行，用按钮展开全文（write 正文）。
   */
  previewLines?: number
}

/** 任务时间线中 write 正文折叠阈值（对话区 write 默认可全文滚动，不用此行数裁剪） */
export const COMPOSER_WRITE_PREVIEW_LINES = 8

/** 单轮 Action 折叠块 */
export interface ComposerActionBlock {
  id: string
  subtitle?: string
  body: string
  /** 内置 read/write/shell 等：结构化小节 + 代码块样式（优先于纯文本 body） */
  panels?: ComposerToolActionPanel[]
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
  return rounds.reduce((n, r) => {
    const actionLen =
      r.action?.panels && r.action.panels.length > 0
        ? r.action.panels.reduce((m, p) => m + p.content.length, 0)
        : (r.action?.body.length ?? 0)
    return n + r.thought.length + actionLen
  }, 0)
}

/** 与上一轮 ``thought`` 经 trim 后全文相同则不再重复展示 Thought 折叠块（Action 仍照常展示） */
export function shouldShowComposerRoundThought(
  rounds: ComposerRoundSegment[],
  index: number,
): boolean {
  if (index < 0 || index >= rounds.length) return false
  const t = rounds[index]!.thought.trim()
  if (!t) return false
  if (index === 0) return true
  return t !== rounds[index - 1]!.thought.trim()
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>
  return null
}

function pickStr(r: Record<string, unknown> | null, key: string): string {
  if (!r) return ''
  const v = r[key]
  return typeof v === 'string' ? v : ''
}

/** 优先使用后端附带的 args_for_display（路径已为绝对路径）。 */
function toolCallArgsForComposer(p: Record<string, unknown>): Record<string, unknown> {
  const disp = p.args_for_display
  if (disp && typeof disp === 'object' && !Array.isArray(disp)) {
    return disp as Record<string, unknown>
  }
  return asRecord(p.args) ?? {}
}

/** shell 的 args.commands 转成多行文本（与任务时间线一致）。 */
function formatShellCommandsForComposer(args: unknown): string {
  const r = asRecord(args)
  if (!r) return ''
  const c = r.commands
  if (typeof c === 'string') return c.trim()
  if (Array.isArray(c)) {
    return c
      .map((x) => String(x).trim())
      .filter(Boolean)
      .join('\n')
  }
  return ''
}

/**
 * 对话区 Action 正文：避免对 write_file.text 等整段 JSON.stringify 导致 \\n 无法换行。
 */
function formatToolCallPayload(payload: Record<string, unknown> | null): string {
  if (!payload) return ''
  const toolRaw = payload.tool
  if (typeof toolRaw !== 'string' || !toolRaw.trim()) return ''
  const tool = toolRaw.trim()
  const argsObj = toolCallArgsForComposer(payload)

  if (tool === 'read_file') {
    const path = pickStr(argsObj, 'file_path')
    return `调用工具：${tool}\n绝对路径：\n${path || '—'}`
  }
  if (tool === 'write_file') {
    const path = pickStr(argsObj, 'file_path')
    const text = pickStr(argsObj, 'text')
    const append = argsObj.append === true
    const mode = append ? '追加' : '覆盖'
    return [
      `调用工具：${tool}`,
      `绝对路径：${path || '—'}`,
      `模式：${mode}`,
      '',
      '── 写入内容 ──',
      text || '（空）',
    ].join('\n')
  }
  if (tool === 'shell') {
    const cmds = formatShellCommandsForComposer(argsObj)
    return [`调用工具：${tool}`, '', '── 命令 ──', cmds || '—'].join('\n')
  }
  if (tool === 'list_directory') {
    const path = pickStr(argsObj, 'dir_path')
    return `调用工具：${tool}\n绝对路径：\n${path || '—'}`
  }

  try {
    return `调用工具：${tool}\n${JSON.stringify(argsObj, null, 2)}`
  } catch {
    return `调用工具：${tool}`
  }
}

function formatToolResultValue(result: unknown): string {
  if (result === null || result === undefined) return '（无）'
  if (typeof result === 'string') return result
  try {
    return JSON.stringify(result, null, 2)
  } catch {
    return String(result)
  }
}

/** 紧随 tool_call 的 tool_result 列表格式化为可读块（对话区 appended 到 Action）。 */
function formatToolResultsForComposer(toolName: string, results: TaskEvent[]): string {
  if (results.length === 0) return ''
  const lines: string[] = ['── 工具调用结果 ──']
  for (const r of results) {
    const p = r.payload as Record<string, unknown> | null
    const ok = p?.ok === true
    const attempt = typeof p?.attempt === 'number' ? p.attempt : null
    const err = p?.error
    lines.push('')
    lines.push(`尝试 ${attempt ?? '—'} · ${ok ? '成功' : '失败'}`)
    if (err != null && err !== '') {
      lines.push(typeof err === 'string' ? err : formatToolResultValue(err))
    }
    if (toolName === 'read_file') {
      lines.push('── 读取到的内容 ──')
      lines.push(formatToolResultValue(p?.result))
    } else if (toolName === 'write_file') {
      if (p?.result !== null && p?.result !== undefined) {
        lines.push('── 工具返回 ──')
        lines.push(formatToolResultValue(p.result))
      }
    } else if (toolName === 'shell') {
      lines.push('── 命令输出 ──')
      lines.push(formatToolResultValue(p?.result))
    } else {
      lines.push('── 返回 ──')
      lines.push(formatToolResultValue(p?.result))
    }
  }
  return lines.join('\n').trimEnd()
}

/**
 * 取某次 tool_call 之后、上界 seq 之前、连续紧随的 tool_result（含多次重试）。
 * 中间若出现其它事件则中断，避免误吞后续步骤的结果。
 */
function toolResultsFollowingCall(
  sortedAsc: TaskEvent[],
  callSeq: number,
  upperSeq: number,
): TaskEvent[] {
  const slice = sortedAsc.filter((e) => e.seq > callSeq && e.seq < upperSeq)
  const out: TaskEvent[] = []
  for (const ev of slice) {
    if (ev.kind === 'tool_result') {
      out.push(ev)
      continue
    }
    if (out.length > 0) break
  }
  return out
}

function toolResultAttemptPlain(r: TaskEvent): string {
  const rp = r.payload as Record<string, unknown> | null
  const ok = rp?.ok === true
  const attempt = typeof rp?.attempt === 'number' ? rp.attempt : null
  const err = rp?.error
  const lines: string[] = [`尝试 ${attempt ?? '—'} · ${ok ? '成功' : '失败'}`]
  if (err != null && err !== '') {
    lines.push(typeof err === 'string' ? err : formatToolResultValue(err))
  }
  return lines.join('\n')
}

function buildReadFileComposerBlock(
  seq: number,
  p: Record<string, unknown>,
  followingResults?: TaskEvent[],
): ComposerActionBlock {
  const argsObj = toolCallArgsForComposer(p)
  const path = pickStr(argsObj, 'file_path')
  const panels: ComposerToolActionPanel[] = [
    {
      id: 'meta',
      variant: 'plain',
      content: `绝对路径：${path || '—'}`,
      copyText: path || undefined,
    },
  ]
  if (followingResults?.length) {
    for (const r of followingResults) {
      panels.push({
        id: `attempt-${r.seq}`,
        variant: 'plain',
        content: toolResultAttemptPlain(r),
      })
      const rp = r.payload as Record<string, unknown> | null
      panels.push({
        id: `read-${r.seq}`,
        title: '读取到的文件内容',
        variant: 'code',
        collapsible: true,
        content: formatToolResultValue(rp?.result),
      })
    }
  }
  return { id: `tool-${seq}`, subtitle: 'read_file', body: '', panels }
}

function buildWriteFileComposerBlock(
  seq: number,
  p: Record<string, unknown>,
  followingResults?: TaskEvent[],
): ComposerActionBlock {
  const argsObj = toolCallArgsForComposer(p)
  const path = pickStr(argsObj, 'file_path')
  const text = pickStr(argsObj, 'text')
  const append = argsObj.append === true
  const mode = append ? '追加' : '覆盖'
  const panels: ComposerToolActionPanel[] = [
    {
      id: 'meta',
      variant: 'plain',
      content: `绝对路径：${path || '—'}\n模式：${mode}`,
      copyText: path || undefined,
    },
    {
      id: 'text',
      title: '写入内容',
      variant: 'code',
      content: text || '（空）',
    },
  ]
  if (followingResults?.length) {
    for (const r of followingResults) {
      panels.push({
        id: `attempt-${r.seq}`,
        variant: 'plain',
        content: toolResultAttemptPlain(r),
      })
      const rp = r.payload as Record<string, unknown> | null
      if (rp?.result !== null && rp?.result !== undefined) {
        panels.push({
          id: `ack-${r.seq}`,
          title: '工具返回',
          variant: 'plain',
          content: formatToolResultValue(rp.result),
        })
      }
    }
  }
  return { id: `tool-${seq}`, subtitle: 'write_file', body: '', panels }
}

function buildListDirectoryComposerBlock(
  seq: number,
  p: Record<string, unknown>,
  followingResults?: TaskEvent[],
): ComposerActionBlock {
  const argsObj = toolCallArgsForComposer(p)
  const path = pickStr(argsObj, 'dir_path')
  const panels: ComposerToolActionPanel[] = [
    {
      id: 'meta',
      variant: 'plain',
      content: `列出目录（绝对路径）：${path || '—'}`,
      copyText: path || undefined,
    },
  ]
  if (followingResults?.length) {
    for (const r of followingResults) {
      panels.push({
        id: `attempt-${r.seq}`,
        variant: 'plain',
        content: toolResultAttemptPlain(r),
      })
      const rp = r.payload as Record<string, unknown> | null
      panels.push({
        id: `listing-${r.seq}`,
        title: '列举结果',
        variant: 'code',
        collapsible: true,
        content: formatToolResultValue(rp?.result),
      })
    }
  }
  return { id: `tool-${seq}`, subtitle: 'list_directory', body: '', panels }
}

function buildShellComposerBlock(
  seq: number,
  p: Record<string, unknown>,
  followingResults?: TaskEvent[],
): ComposerActionBlock {
  const argsObj = asRecord(p.args) ?? {}
  const cmds = formatShellCommandsForComposer(argsObj)
  const panels: ComposerToolActionPanel[] = [
    { id: 'cmd', title: '命令', variant: 'code', content: cmds || '—' },
  ]
  if (followingResults?.length) {
    for (const r of followingResults) {
      panels.push({
        id: `attempt-${r.seq}`,
        variant: 'plain',
        content: toolResultAttemptPlain(r),
      })
      const rp = r.payload as Record<string, unknown> | null
      panels.push({
        id: `out-${r.seq}`,
        title: '命令输出',
        variant: 'code',
        collapsible: true,
        content: formatToolResultValue(rp?.result),
      })
    }
  }
  return { id: `tool-${seq}`, subtitle: 'shell', body: '', panels }
}

/** 连续多条 tool_call 且 tool 名相同时，合并为同一 Action 展示（按序插入「第 N 次调用」分界）。 */
function mergeComposerActionBlocksForSameTool(
  blocks: ComposerActionBlock[],
  toolLabel: string,
): ComposerActionBlock | null {
  const ok = blocks.filter(Boolean)
  if (ok.length === 0) return null
  if (ok.length === 1) return ok[0]!
  const mergedPanels: ComposerToolActionPanel[] = []
  for (let i = 0; i < ok.length; i++) {
    const b = ok[i]!
    if (i > 0) {
      mergedPanels.push({
        id: `${b.id}-sep`,
        variant: 'plain',
        content: `第 ${i + 1} 次调用`,
      })
    }
    if (b.panels?.length) {
      for (const p of b.panels) {
        mergedPanels.push({ ...p, id: `${b.id}__${p.id}` })
      }
    } else if (b.body.trim()) {
      mergedPanels.push({
        id: `${b.id}-body`,
        title: i > 0 ? `正文（第 ${i + 1} 次）` : undefined,
        variant: 'code',
        collapsible: true,
        content: b.body,
      })
    }
  }
  return {
    id: ok.map((b) => b.id).join('+'),
    subtitle: `${toolLabel} · ${ok.length} 次`,
    body: '',
    panels: mergedPanels,
  }
}

function toolCallNameKey(e: TaskEvent): string {
  if (e.kind !== 'tool_call' || !e.payload || typeof e.payload !== 'object') return ''
  const t = (e.payload as Record<string, unknown>).tool
  if (typeof t === 'string' && t.trim()) return t.trim()
  return `\0${e.seq}`
}

function toolCallLocalThought(p: Record<string, unknown> | undefined): string {
  return p && typeof p.thought === 'string' ? p.thought.trim() : ''
}

/**
 * 当前 thought 子段在组内首条下标 chunkFirstG 处展示用文案；
 * 仅与同组首条 chunk 合并「该 tool_call 之前」时间窗内的流式 thinking（preToolStream），
 * 避免把整段步进/全局缓冲的思考提前糊到第一轮或塞进后续 react。
 */
function thoughtForToolCallChunk(
  group: TaskEvent[],
  chunkFirstG: number,
  preToolStreamThought: string,
): string {
  const localTh = toolCallLocalThought(
    group[chunkFirstG]!.payload as Record<string, unknown> | undefined,
  )
  if (chunkFirstG === 0) {
    return mergeThoughtDisplayParts(preToolStreamThought, localTh).trim()
  }
  return localTh
}

/**
 * tool 组结束后推进流式切片上界：包含组内最后一次 tool_call 及其后紧随的 tool_result，
 * 以便其后的 llm_stream_delta 归入下一轮而非倒灌进上一轮 Thought。
 */
function maxSeqAfterToolGroup(
  scopedAsc: TaskEvent[],
  group: TaskEvent[],
  nextAfterGroup: TaskEvent | undefined,
  maxSeq: number,
): number {
  const upperBound = nextAfterGroup?.seq ?? maxSeq
  const lastCall = group[group.length - 1]!.seq
  let mx = lastCall
  let seenResultAfterCall = false
  for (const ev of scopedAsc) {
    if (ev.seq <= lastCall) continue
    if (ev.seq >= upperBound) break
    if (ev.kind === 'tool_result') {
      mx = Math.max(mx, ev.seq)
      seenResultAfterCall = true
      continue
    }
    if (seenResultAfterCall) break
  }
  return mx
}

/**
 * 连续相同工具的一组 tool_call 内，按「连续相同 thought」再分子段：仅归一化后的 thought 相同且连续才留在同一段；
 * 空 thought 视为延续当前段（不新起一段）。
 */
function chunkGroupIndicesByConsecutiveThought(
  group: TaskEvent[],
  preToolStreamThought: string,
): number[][] {
  const chunks: number[][] = []
  for (let g = 0; g < group.length; g++) {
    const localTh = toolCallLocalThought(group[g]!.payload as Record<string, unknown> | undefined)
    if (chunks.length === 0) {
      chunks.push([g])
      continue
    }
    const cur = chunks[chunks.length - 1]!
    if (!localTh) {
      cur.push(g)
      continue
    }
    const displayFirst = thoughtForToolCallChunk(group, cur[0]!, preToolStreamThought)
    if (collapseWs(localTh) === collapseWs(displayFirst)) {
      cur.push(g)
    } else {
      chunks.push([g])
    }
  }
  return chunks
}

/**
 * 将 reactOrdered（tool_call | react_turn 交错）转为 ComposerRoundSegment；
 * 连续相同 tool 名的 tool_call 合并为一轮 Action。
 *
 * streamLowerSeq：已消费的 llm_stream_delta 上界（通常为 0 或当前 step_start.seq）；
 * 仅将「各 react 节点 seq 之前」时间窗内的流式 thinking 并入该节点，避免整段缓冲倒序灌入首轮。
 */
function appendSegmentsFromReactOrdered(
  reactOrdered: TaskEvent[],
  scopedAsc: TaskEvent[],
  streamLowerSeq: number,
  maxSeq: number,
  out: ComposerRoundSegment[],
  roundIndexMode: 'fromOutLength' | 'incremental',
  incrementalCounter: { n: number } | null,
  opts?: { stepThoughtPrefix?: string },
): void {
  let streamCutSeq = streamLowerSeq
  let pendingStepPrefix = (opts?.stepThoughtPrefix ?? '').trim()

  const mergeFirstSliceThought = (streamPart: string, localPart: string): string => {
    const inner = mergeThoughtDisplayParts(streamPart.trim(), localPart.trim()).trim()
    if (pendingStepPrefix) {
      const outThought = mergeThoughtDisplayParts(pendingStepPrefix, inner).trim()
      pendingStepPrefix = ''
      return outThought
    }
    return inner
  }

  let j = 0
  while (j < reactOrdered.length) {
    const e = reactOrdered[j]!
    if (e.kind === 'react_turn') {
      const p = e.payload as Record<string, unknown> | undefined
      const localTh =
        p && typeof p.thought === 'string' ? p.thought.trim() : ''
      const slice = foldLlmStreamDeltasInSeqRange(scopedAsc, streamCutSeq, e.seq - 1)
      const sm = mergeAnswerThinkIntoDisplayThinking(slice.thinking, slice.answer)
      const streamPart = sm.thinking.trim()
      const thought = mergeFirstSliceThought(streamPart, localTh)
      streamCutSeq = e.seq
      j += 1
      if (!thought) continue
      const roundIndex =
        roundIndexMode === 'fromOutLength'
          ? out.length + 1
          : ++incrementalCounter!.n
      out.push({
        id: `rt-${e.seq}`,
        roundIndex,
        thought,
        action: null,
      })
      continue
    }
    if (e.kind !== 'tool_call') {
      j += 1
      continue
    }
    const key0 = toolCallNameKey(e)
    const group: TaskEvent[] = [e]
    let k = j + 1
    while (k < reactOrdered.length) {
      const next = reactOrdered[k]!
      if (next.kind !== 'tool_call') break
      if (toolCallNameKey(next) !== key0) break
      group.push(next)
      k++
    }
    const nextAfterGroup = reactOrdered[k]

    const firstToolSeq = group[0]!.seq
    const preToolSlice = foldLlmStreamDeltasInSeqRange(
      scopedAsc,
      streamCutSeq,
      firstToolSeq - 1,
    )
    const preToolMerged = mergeAnswerThinkIntoDisplayThinking(
      preToolSlice.thinking,
      preToolSlice.answer,
    )
    let preToolStreamThought = preToolMerged.thinking.trim()
    if (pendingStepPrefix) {
      preToolStreamThought = mergeThoughtDisplayParts(
        pendingStepPrefix,
        preToolStreamThought,
      ).trim()
      pendingStepPrefix = ''
    }

    const thoughtChunks = chunkGroupIndicesByConsecutiveThought(group, preToolStreamThought)
    for (const idxs of thoughtChunks) {
      const blocks: ComposerActionBlock[] = []
      for (const g of idxs) {
        const ev = group[g]!
        const upper =
          g + 1 < group.length
            ? group[g + 1]!.seq
            : nextAfterGroup?.seq ?? maxSeq
        const results = toolResultsFollowingCall(scopedAsc, ev.seq, upper)
        const block = toolEventToBlock(ev, results)
        if (block) blocks.push(block)
      }

      const thought = thoughtForToolCallChunk(group, idxs[0]!, preToolStreamThought)

      if (blocks.length > 0) {
        const firstG = idxs[0]!
        const p0 = group[firstG]!.payload as Record<string, unknown> | undefined
        const t0 = p0 && typeof p0.tool === 'string' ? p0.tool.trim() : ''
        const toolLabel = t0 || blocks[0]!.subtitle?.trim() || '工具'
        const mergedAction =
          blocks.length === 1
            ? blocks[0]!
            : mergeComposerActionBlocksForSameTool(blocks, toolLabel)
        const roundIndex =
          roundIndexMode === 'fromOutLength'
            ? out.length + 1
            : ++incrementalCounter!.n
        out.push({
          id: idxs.map((g) => `tc-${group[g]!.seq}`).join('+'),
          roundIndex,
          thought,
          action: mergedAction,
        })
      } else if (thought.trim()) {
        const roundIndex =
          roundIndexMode === 'fromOutLength'
            ? out.length + 1
            : ++incrementalCounter!.n
        out.push({
          id: idxs.map((g) => `tc-${group[g]!.seq}`).join('+'),
          roundIndex,
          thought,
          action: null,
        })
      }
    }
    streamCutSeq = maxSeqAfterToolGroup(scopedAsc, group, nextAfterGroup, maxSeq)
    j = k
  }
}

function toolEventToBlock(e: TaskEvent, followingResults?: TaskEvent[]): ComposerActionBlock | null {
  if (e.kind !== 'tool_call' || !e.payload || typeof e.payload !== 'object') return null
  const p = e.payload as Record<string, unknown>
  const tool = typeof p.tool === 'string' ? p.tool.trim() : ''
  if (!tool) return null

  if (tool === 'read_file') {
    return buildReadFileComposerBlock(e.seq, p, followingResults)
  }
  if (tool === 'write_file') {
    return buildWriteFileComposerBlock(e.seq, p, followingResults)
  }
  if (tool === 'list_directory') {
    return buildListDirectoryComposerBlock(e.seq, p, followingResults)
  }
  if (tool === 'shell') {
    return buildShellComposerBlock(e.seq, p, followingResults)
  }

  const callPart = formatToolCallPayload(p)
  if (!callPart) return null
  const resultPart =
    followingResults && followingResults.length > 0
      ? formatToolResultsForComposer(tool, followingResults)
      : ''
  const body = resultPart ? `${callPart}\n\n${resultPart}` : callPart
  return { id: `tool-${e.seq}`, subtitle: tool, body }
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
  const scoped = sliceTaskEventsForActivePlanCycle(sorted)
  const folded = foldLlmStreamDeltasSorted(scoped, { onlySinceLastStepStart: true })
  const merged = mergeAnswerThinkIntoDisplayThinking(folded.thinking, folded.answer)
  const stepFall = lastCommittedThoughtFromStepStartsSorted(scoped)
  const thinking = merged.thinking || stepFall
  const streamAction = folded.action
  const fromTool = lastToolCallActionSinceLastStepSorted(scoped)
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
  const scoped = sliceTaskEventsForActivePlanCycle(sorted)
  const stepStarts = scoped.filter((e) => e.kind === 'step_start')
  const maxSeq = Number.MAX_SAFE_INTEGER

  if (stepStarts.length === 0) {
    const stream = foldLlmStreamDeltasInSeqRange(scoped, 0, maxSeq)
    const merged = mergeAnswerThinkIntoDisplayThinking(stream.thinking, stream.answer)
    const streamThought = merged.thinking.trim()
    const reactOrdered = scoped
      .filter((e) => e.kind === 'tool_call' || e.kind === 'react_turn')
      .sort((a, b) => a.seq - b.seq)

    if (reactOrdered.length > 0) {
      const scopedAsc = [...scoped].sort((a, b) => a.seq - b.seq)
      const segments: ComposerRoundSegment[] = []
      appendSegmentsFromReactOrdered(
        reactOrdered,
        scopedAsc,
        0,
        maxSeq,
        segments,
        'fromOutLength',
        null,
      )
      if (segments.length > 0) return segments
    }

    let action: ComposerActionBlock | null = null
    const tools = scoped.filter((e) => e.kind === 'tool_call')
    const lastTool = tools[tools.length - 1]
    if (lastTool) {
      const scopedAsc = [...scoped].sort((a, b) => a.seq - b.seq)
      const results = toolResultsFollowingCall(scopedAsc, lastTool.seq, maxSeq)
      action = toolEventToBlock(lastTool, results)
    } else if (stream.action.trim()) {
      action = {
        id: 'stream-0',
        subtitle: busy ? '进行中' : '流式',
        body: stream.action,
      }
    }
    if (!streamThought && !action) return []
    return [{ id: 'r1', roundIndex: 1, thought: streamThought, action }]
  }

  const out: ComposerRoundSegment[] = []
  let roundCounter = 0
  for (let i = 0; i < stepStarts.length; i++) {
    const ss = stepStarts[i]!
    const nextSeq = stepStarts[i + 1]?.seq ?? maxSeq
    const stream = foldLlmStreamDeltasInSeqRange(scoped, ss.seq, nextSeq)
    const merged = mergeAnswerThinkIntoDisplayThinking(stream.thinking, stream.answer)
    const rawThought =
      typeof ss.payload?.thought === 'string' ? ss.payload.thought.trim() : ''
    const baseThought = mergeThoughtDisplayParts(rawThought, merged.thinking).trim()

    const inStep = scoped.filter((e) => e.seq > ss.seq && e.seq < nextSeq)
    const inStepAsc = [...inStep].sort((a, b) => a.seq - b.seq)
    const reactOrdered = inStep
      .filter((e) => e.kind === 'tool_call' || e.kind === 'react_turn')
      .sort((a, b) => a.seq - b.seq)

    if (reactOrdered.length > 0) {
      const ctr = { n: roundCounter }
      appendSegmentsFromReactOrdered(
        reactOrdered,
        inStepAsc,
        ss.seq,
        nextSeq,
        out,
        'incremental',
        ctr,
        { stepThoughtPrefix: rawThought },
      )
      roundCounter = ctr.n
      continue
    }

    const toolsInRange = scoped.filter(
      (e) => e.kind === 'tool_call' && e.seq > ss.seq && e.seq <= nextSeq,
    )
    const lastTool = toolsInRange[toolsInRange.length - 1]
    let action: ComposerActionBlock | null = null
    if (lastTool) {
      const results = toolResultsFollowingCall(inStepAsc, lastTool.seq, nextSeq)
      action = toolEventToBlock(lastTool, results)
    } else if (stream.action.trim()) {
      action = {
        id: `stream-${ss.seq}`,
        subtitle: busy ? '进行中' : '流式',
        body: stream.action,
      }
    }

    roundCounter += 1
    const sid =
      typeof ss.payload?.step_id === 'string' && ss.payload.step_id.trim()
        ? ss.payload.step_id
        : `step-${ss.seq}`

    out.push({
      id: sid,
      roundIndex: roundCounter,
      thought: baseThought,
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
