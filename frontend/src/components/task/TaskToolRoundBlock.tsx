/**
 * 执行模块（前端可观测）：单计划步时间线，按 seq 展示多轮 ReAct 与终答。
 */

import type { ReactNode } from 'react'
import { useState } from 'react'
import { CopyTextButton } from '@/components/common/CopyTextButton'
import { formatDateTime } from '@/utils/format'
import type { TaskEvent } from '@/types/task'
import { COMPOSER_WRITE_PREVIEW_LINES } from '@/utils/foldComposerLlmStream'

/** 单步子时间线所需事件列表。 */
export interface TaskToolRoundBlockProps {
  events: TaskEvent[]
}

/** 读取 payload 中的字符串字段，缺省或非字符串时返回空串。 */
function pickPayloadString(p: Record<string, unknown> | null, key: string): string {
  if (!p) return ''
  const v = p[key]
  return typeof v === 'string' ? v : ''
}

/** 将值格式化为缩进 JSON 文本；不可序列化时退回 String。 */
function formatJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

/** 将未知值安全视为对象字典。 */
function asRecord(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    return v as Record<string, unknown>
  }
  return null
}

/** 读取对象上的字符串字段。 */
function pickStr(r: Record<string, unknown> | null, key: string): string {
  if (!r) return ''
  const v = r[key]
  return typeof v === 'string' ? v : ''
}

/** 判断是否为常见绝对路径形式（含 Windows 盘符）。 */
function isProbablyAbsolutePath(p: string): boolean {
  if (!p) return false
  if (p.startsWith('\\\\')) return true
  if (/^[A-Za-z]:[\\/]/.test(p)) return true
  if (p.startsWith('/')) return true
  return false
}

/** 将工作区根与相对路径拼成展示用绝对路径（浏览器侧简单拼接）。 */
function joinWorkspaceAbsolute(root: string, relative: string): string {
  const r = root.replace(/[/\\]+$/, '')
  const rel = relative.replace(/^[/\\]+/, '')
  const sep = root.includes('\\') ? '\\' : '/'
  return `${r}${sep}${rel}`
}

/** 无后端 args_for_display 时，用 step 快照中的 workspace_root 将路径转为绝对路径展示。 */
function clientResolveToolPathsForDisplay(
  toolName: string,
  args: unknown,
  workspaceRoot: string,
): unknown {
  if (!workspaceRoot.trim()) return args
  const rec = asRecord(args)
  if (!rec) return args
  const out: Record<string, unknown> = { ...rec }
  if (toolName === 'read_file' || toolName === 'write_file') {
    const fp = pickStr(rec, 'file_path')
    if (fp && !isProbablyAbsolutePath(fp)) {
      out.file_path = joinWorkspaceAbsolute(workspaceRoot, fp)
    }
  } else if (toolName === 'list_directory') {
    const dp = pickStr(rec, 'dir_path')
    if (!dp.trim() || dp.trim() === '.') {
      out.dir_path = workspaceRoot
    } else if (!isProbablyAbsolutePath(dp)) {
      out.dir_path = joinWorkspaceAbsolute(workspaceRoot, dp)
    }
  }
  return out
}

/** 从 step_start 取 workspace_root，供工具参数在缺省 args_for_display 时拼绝对路径。 */
function workspaceRootFromStepStart(stepStart: TaskEvent | undefined): string {
  const p = stepStart?.payload
  if (!p) return ''
  const root = p.workspace_root
  return typeof root === 'string' ? root.trim() : ''
}

/** shell 工具的 commands 参数格式化为可展示的多行文本。 */
function formatShellCommands(args: unknown): string {
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

const codePreClass =
  'max-h-[min(18rem,45vh)] overflow-auto rounded-md bg-neutral-900/90 p-2.5 font-mono text-xs text-neutral-100 whitespace-pre-wrap break-words'

/** 工具 result：字符串含换行时按多行展示。 */
function formatToolResultBody(data: unknown): { text: string; preWrap: boolean } {
  if (data === null || data === undefined) {
    return { text: formatJson(data), preWrap: false }
  }
  if (typeof data === 'string') {
    if (data.includes('\n') || data.includes('\\n')) {
      const normalized = data.includes('\n') ? data : data.replace(/\\n/g, '\n')
      return { text: normalized, preWrap: true }
    }
    return { text: data, preWrap: false }
  }
  return { text: formatJson(data), preWrap: false }
}

type ToolCallWithResults = {
  call: TaskEvent
  results: TaskEvent[]
}

type ToolReactTurn = {
  kind: 'tool'
  round: number
  thought: string
  tools: ToolCallWithResults[]
}

type FinalReactTurn = {
  kind: 'final'
  round: number
  thought: string
  finalAnswer: boolean
  seq: number
  /** true when backend sent final_answer:true (boolean) indicating sub-goal satisfied */
  isCompleted: boolean
}

/** 按 seq 归并 tool_call、挂接 tool_result，并收录带 final_answer 的 react_turn。
 * 
 * 核心逻辑：一轮 ReAct 可能包含多个并行工具调用（通过 actions 数组），
 * 这些 tool_call 事件是连续的且共享相同的 thought。
 * 将它们归为一轮展示，体现真正的并行执行语义。
 */
function buildReactTurns(events: TaskEvent[]): (ToolReactTurn | FinalReactTurn)[] {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const turns: (ToolReactTurn | FinalReactTurn)[] = []
  let round = 0
  let currentToolTurn: ToolReactTurn | null = null

  for (const e of sorted) {
    if (e.kind === 'tool_call') {
      const p = e.payload as Record<string, unknown> | null
      const thought = p && typeof p.thought === 'string' ? p.thought.trim() : ''
      
      // 判断是否属于当前轮：
      // 1. 当前没有活跃的 tool 轮，或
      // 2. thought 不同（说明是新的 LLM 输出）
      if (!currentToolTurn || currentToolTurn.thought !== thought) {
        round += 1
        currentToolTurn = { kind: 'tool', round, thought, tools: [] }
        turns.push(currentToolTurn)
      }
      
      // 将 tool_call 添加到当前轮的工具列表中
      currentToolTurn.tools.push({ call: e, results: [] })
    } else if (e.kind === 'tool_result') {
      // 将结果挂到当前轮最后一个工具上
      if (currentToolTurn && currentToolTurn.tools.length > 0) {
        const lastTool = currentToolTurn.tools[currentToolTurn.tools.length - 1]
        lastTool.results.push(e)
      }
    } else if (e.kind === 'react_turn') {
      // 若带终答则单独成轮，便于与工具轮并列展示
      const p = e.payload as Record<string, unknown> | null
      const thought = p && typeof p.thought === 'string' ? p.thought.trim() : ''
      const faRaw = p?.final_answer
      // final_answer 现在是 boolean 类型；true 表示"子目标满足可结束"
      // 兼容旧格式："completed" 字符串也视为 true
      const isCompleted = faRaw === true || faRaw === 'completed'
      const fa = typeof faRaw === 'boolean' ? faRaw : (typeof faRaw === 'string' ? faRaw.trim() === 'completed' : false)
      if (fa) {
        round += 1
        currentToolTurn = null
        turns.push({ kind: 'final', round, thought, finalAnswer: true, seq: e.seq, isCompleted })
      }
    }
  }
  return turns
}

/** 从步内事件提取标题、起止状态、工具成败与兜底摘抄等展示元数据。 */
function analyzeStepMeta(events: TaskEvent[]) {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const stepStart = sorted.find((ev) => ev.kind === 'step_start')
  const stepEnd = sorted.find((ev) => ev.kind === 'step_end')
  const toolResults = sorted.filter((ev) => ev.kind === 'tool_result')
  const toolResultLast = toolResults.length ? toolResults[toolResults.length - 1] : undefined
  const title =
    pickPayloadString(stepStart?.payload ?? null, 'title').trim() || '本步执行'
  const headerThought = pickPayloadString(stepStart?.payload ?? null, 'thought').trim()
  const endStatus =
    typeof stepEnd?.payload?.status === 'string' ? stepEnd.payload.status : ''
  const rawExcerpt =
    typeof stepEnd?.payload?.raw_excerpt === 'string'
      ? stepEnd.payload.raw_excerpt.trim()
      : ''
  const toolOk = toolResultLast?.payload?.ok === true
  const hadAnyToolAttempt = toolResults.length > 0
  const firstSeq = events.reduce((m, e) => Math.min(m, e.seq), events[0]?.seq ?? 0)
  const ts = stepStart?.ts ?? events[0]?.ts ?? ''
  return {
    title,
    headerThought,
    endStatus,
    rawExcerpt,
    toolOk,
    hadAnyToolAttempt,
    firstSeq,
    ts,
    stepStart,
  }
}

/** 根据 step_end 状态与工具结果映射徽标文案、样式与可选提示。 */
function resolveStepEndBadge(
  endStatus: string,
  toolOk: boolean,
  hadAnyToolAttempt: boolean,
): { label: string; badgeClass: string; hint?: string } {
  if (endStatus === 'ok' || endStatus === 'final_answer') {
    return {
      label: endStatus === 'ok' ? '已完成' : endStatus,
      badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    }
  }
  if (endStatus === 'skipped_no_tool') {
    return {
      label: '已跳过',
      badgeClass: 'bg-neutral-100 text-neutral-700 border-neutral-200',
    }
  }
  if (
    endStatus === 'parse_error' ||
    endStatus === 'invalid_react_shape' ||
    endStatus === 'unknown_tool'
  ) {
    return {
      label: endStatus,
      badgeClass: 'bg-amber-50 text-amber-900 border-amber-200',
    }
  }
  if (endStatus === 'failed' && hadAnyToolAttempt && toolOk) {
    return {
      label: '未收官',
      badgeClass: 'bg-amber-50 text-amber-900 border-amber-200',
      hint: '工具已一次或多次返回成功，但本子步未在后续轮次产出 final_answer、或解析失败。',
    }
  }
  if (endStatus === 'failed') {
    return {
      label: '失败',
      badgeClass: 'bg-red-50 text-red-800 border-red-200',
    }
  }
  return {
    label: endStatus,
    badgeClass: 'bg-red-50 text-red-800 border-red-200',
  }
}

/** 从 tool_call 解析工具名、原始参数与展示用参数（路径类已为绝对路径）。 */
function toolCallNameArgs(ev: TaskEvent): {
  name: string
  args: unknown
  argsForDisplay: unknown
} {
  const p = ev.payload as Record<string, unknown> | null
  const name = p && typeof p.tool === 'string' ? p.tool : ''
  const rawArgs = p?.args ?? {}
  const disp = p?.args_for_display
  const argsForDisplay =
    disp && typeof disp === 'object' && !Array.isArray(disp) ? disp : rawArgs
  return { name, args: rawArgs, argsForDisplay }
}

/** 内置工具：Action 区展示与 JSON 不同的结构化参数；非以上工具返回 null 以便回退 JSON。 */
function renderBuiltinToolActionBody(toolName: string, args: unknown): ReactNode {
  const rec = asRecord(args)
  if (toolName === 'read_file') {
    const path = pickStr(rec, 'file_path')
    return (
      <div className="space-y-1.5 text-xs">
        <p className="font-medium text-neutral-600">读取文件（绝对路径）</p>
        <div className="flex flex-wrap items-start gap-2">
          <pre className={`${codePreClass} min-w-0 flex-1`}>{path || '—'}</pre>
          {path ? <CopyTextButton text={path} label="复制路径" /> : null}
        </div>
      </div>
    )
  }
  if (toolName === 'write_file') {
    const path = pickStr(rec, 'file_path')
    const append = rec?.append === true
    return (
      <div className="space-y-1.5 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-neutral-600">写入文件（绝对路径）</p>
          {append ? (
            <span className="rounded bg-amber-100/80 px-1.5 py-0.5 text-amber-900">追加模式</span>
          ) : (
            <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-neutral-600">覆盖写入</span>
          )}
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <pre className={`${codePreClass} min-w-0 flex-1`}>{path || '—'}</pre>
          {path ? <CopyTextButton text={path} label="复制路径" /> : null}
        </div>
        <p className="text-neutral-500">写入正文在下方「工具调用结果」中展示。</p>
      </div>
    )
  }
  if (toolName === 'list_directory') {
    const path = pickStr(rec, 'dir_path')
    return (
      <div className="space-y-1.5 text-xs">
        <p className="font-medium text-neutral-600">列出目录（绝对路径）</p>
        <div className="flex flex-wrap items-start gap-2">
          <pre className={`${codePreClass} min-w-0 flex-1`}>{path || '—'}</pre>
          {path ? <CopyTextButton text={path} label="复制路径" /> : null}
        </div>
      </div>
    )
  }
  if (toolName === 'shell') {
    const cmds = formatShellCommands(args)
    return (
      <div className="space-y-1.5 text-xs">
        <p className="font-medium text-neutral-600">执行的命令</p>
        <pre className={codePreClass}>{cmds || '—'}</pre>
      </div>
    )
  }
  return null
}

/** write 正文：默认全文展示，超长时可收起。 */
function WriteFileInlinePreview({ text, className }: { text: string; className: string }) {
  const lines = text.split(/\r?\n/)
  const n = COMPOSER_WRITE_PREVIEW_LINES
  const hasMore = lines.length > n
  const [expanded, setExpanded] = useState(true)
  const shown = !hasMore || expanded ? text : lines.slice(0, n).join('\n')
  return (
    <div className="space-y-1.5">
      <p className="font-medium text-neutral-700 text-xs">写入的正文</p>
      <pre className={className}>{shown}</pre>
      {hasMore ? (
        <button
          type="button"
          className="fa-link text-xs"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? '收起' : `展开全文（共 ${lines.length} 行）`}
        </button>
      ) : null}
    </div>
  )
}

/** 单条 tool_result：按内置工具类型突出正文，其余仍用 JSON。 */
function ToolAttemptRow({
  ev,
  toolName,
  toolArgs,
}: {
  ev: TaskEvent
  toolName: string
  toolArgs: unknown
}) {
  const p = ev.payload as Record<string, unknown> | null
  const ok = p?.ok === true
  const attempt = typeof p?.attempt === 'number' ? p.attempt : null
  const err = p?.error
  const result = p?.result ?? null
  const argRec = asRecord(toolArgs)

  const errBlock =
    err != null && err !== '' ? (
      <p className="mt-2 text-red-800 text-xs leading-relaxed">
        {typeof err === 'string' ? err : formatJson(err)}
      </p>
    ) : null

  let mainBody: ReactNode = null
  if (toolName === 'read_file') {
    const body = formatToolResultBody(result)
    const contentText = ok ? body.text : body.text || '（未返回内容）'
    mainBody = (
      <div className="fa-chat-block-thinking !mt-2 !p-0">
        <details className="fa-thinking-fold">
          <summary className="fa-thinking-summary">
            <span className="fa-chat-fold-link">读取到的文件内容</span>
            <span className="fa-chat-fold-chevron" aria-hidden>
              ›
            </span>
          </summary>
          <pre
            className={`${codePreClass} mt-1 ${body.preWrap ? '' : 'whitespace-pre-wrap break-words'}`}
          >
            {contentText}
          </pre>
        </details>
      </div>
    )
  } else if (toolName === 'write_file') {
    const path = pickStr(argRec, 'file_path')
    const text = pickStr(argRec, 'text')
    const ack = formatToolResultBody(result)
    const showAck = result !== null && result !== undefined
    mainBody = (
      <div className="mt-2 space-y-3">
        {path ? (
          <div className="flex flex-wrap items-center gap-2 text-neutral-600 text-xs">
            <span>
              目标文件（绝对路径）：{' '}
              <span className="font-mono text-neutral-800">{path}</span>
            </span>
            <CopyTextButton text={path} label="复制路径" />
          </div>
        ) : null}
        <WriteFileInlinePreview
          text={text || '（无 text 参数）'}
          className={codePreClass}
        />
        {showAck ? (
          <div className="space-y-1.5">
            <p className="font-medium text-neutral-700 text-xs">工具返回说明</p>
            <pre className={codePreClass}>{ack.text || '（空）'}</pre>
          </div>
        ) : null}
      </div>
    )
  } else if (toolName === 'shell') {
    const body = formatToolResultBody(result)
    mainBody = (
      <div className="fa-chat-block-thinking !mt-2 !p-0">
        <details className="fa-thinking-fold">
          <summary className="fa-thinking-summary">
            <span className="fa-chat-fold-link">命令输出（含退出码提示）</span>
            <span className="fa-chat-fold-chevron" aria-hidden>
              ›
            </span>
          </summary>
          <pre
            className={`${codePreClass} mt-1 ${body.preWrap ? '' : 'whitespace-pre-wrap break-words'}`}
          >
            {body.text}
          </pre>
        </details>
      </div>
    )
  } else {
    const body = formatToolResultBody(result)
    mainBody = (
      <pre
        className={`mt-2 max-h-[min(16rem,40vh)] overflow-auto rounded-md bg-neutral-900/90 p-2 font-mono text-xs text-neutral-100 ${
          body.preWrap ? 'whitespace-pre-wrap break-words' : ''
        }`}
      >
        {body.text}
      </pre>
    )
  }

  return (
    <div className="rounded border border-neutral-200 bg-neutral-50/80 p-2">
      <p className="font-mono text-neutral-800 text-xs">
        <span className="text-neutral-500">尝试</span> {attempt ?? '—'} ·{' '}
        <span className={ok ? 'text-emerald-700' : 'text-red-700'}>{ok ? '成功' : '失败'}</span>
      </p>
      {errBlock}
      {mainBody}
    </div>
  )
}

/** 展示同一 tool_call 下多次 tool_result（尝试序号、成败、错误与结果体）。 */
function ToolAttemptBlocks({
  results,
  toolName,
  toolArgs,
}: {
  results: TaskEvent[]
  toolName: string
  toolArgs: unknown
}) {
  if (results.length === 0) {
    return <p className="text-neutral-500 text-xs">等待或缺失 tool_result</p>
  }
  return (
    <div className="space-y-2">
      {results.map((r) => (
        <ToolAttemptRow key={r.seq} ev={r} toolName={toolName} toolArgs={toolArgs} />
      ))}
    </div>
  )
}

/** 单轮 ReAct 调用的列表项（Thought / 多个并行 Actions / 各自结果）。
 * 
 * 展示逻辑：
 * - 一次 Thought（该轮的推理）
 * - N 个并行 Action（每个工具一个卡片）
 * - 每个工具的独立结果
 */
function ToolRoundListItem({
  turn,
  workspaceRoot,
}: {
  turn: ToolReactTurn
  workspaceRoot: string
}) {
  const parallelCount = turn.tools.length
  const isParallel = parallelCount > 1
  
  return (
    <li className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-neutral-500">
        <span>轮次 {turn.round}</span>
        {isParallel ? (
          <span className="rounded bg-primary-500/10 px-1.5 py-0.5 font-medium text-primary-700">
            并行 {parallelCount} 个工具
          </span>
        ) : (
          <span>· 工具</span>
        )}
      </div>
      
      {/* Thought：整轮共享的推理 */}
      <div className="fa-chat-block-thinking !p-0">
        <details className="fa-thinking-fold" open>
          <summary className="fa-thinking-summary">
            <span className="fa-chat-fold-link">Thought</span>
            <span className="fa-chat-fold-chevron" aria-hidden>
              ›
            </span>
          </summary>
          {turn.thought ? (
            <pre className="fa-chat-thinking-pre mt-1">{turn.thought}</pre>
          ) : (
            <p className="mt-1 text-neutral-500 text-xs">
              （事件未带 thought，多为运行中的旧任务或模型省略该字段）
            </p>
          )}
        </details>
      </div>

      {/* 并行工具调用列表 */}
      <div className={isParallel ? 'space-y-3' : ''}>
        {turn.tools.map((toolItem, idx) => {
          const { name: toolNm, args: toolArg, argsForDisplay: toolArgDisplay } = toolCallNameArgs(
            toolItem.call,
          )
          const p0 = toolItem.call.payload as Record<string, unknown> | null
          const hasServerDisplay = p0?.args_for_display != null
          const resolvedArgs =
            hasServerDisplay || !workspaceRoot
              ? toolArgDisplay
              : clientResolveToolPathsForDisplay(toolNm, toolArgDisplay, workspaceRoot)
          const builtinAction = renderBuiltinToolActionBody(toolNm, resolvedArgs)

          return (
            <div key={toolItem.call.seq} className={isParallel ? 'rounded-lg border border-neutral-200/80 bg-neutral-50/50 p-2.5 space-y-2' : 'space-y-2'}>
              {/* 工具标题 */}
              {isParallel && (
                <p className="font-mono text-neutral-700 text-xs font-medium flex items-center gap-2">
                  <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary-500/10 text-primary-700 text-[10px]">
                    {idx + 1}
                  </span>
                  {toolNm || '—'}
                </p>
              )}

              {/* Action 详情 */}
              <div className="fa-chat-block-thinking !p-0">
                <details className="fa-thinking-fold" open>
                  <summary className="fa-thinking-summary">
                    <span className="fa-chat-fold-link">
                      {isParallel ? `Action #${idx + 1}` : `Action`} · {toolNm || '—'}
                    </span>
                    <span className="fa-chat-fold-chevron" aria-hidden>
                      ›
                    </span>
                  </summary>
                  <div className="mt-2 space-y-2">
                    {builtinAction ?? (
                      <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-neutral-900/90 p-2.5 font-mono text-xs text-neutral-100">
                        {formatJson(toolArg)}
                      </pre>
                    )}
                    {builtinAction ? (
                      <details className="rounded border border-neutral-200/80 bg-neutral-50/50">
                        <summary className="cursor-pointer px-2 py-1.5 font-mono text-neutral-600 text-xs">
                          原始 JSON 参数
                        </summary>
                        <pre className="max-h-32 overflow-auto border-neutral-200/80 border-t p-2 font-mono text-neutral-800 text-xs">
                          {formatJson(toolArg)}
                        </pre>
                      </details>
                    ) : null}
                  </div>
                </details>
              </div>

              {/* 工具结果 */}
              <div className="fa-chat-block-thinking !p-0">
                <details className="fa-thinking-fold" open>
                  <summary className="fa-thinking-summary">
                    <span className="fa-chat-fold-link">工具调用结果</span>
                    <span className="fa-chat-fold-chevron" aria-hidden>
                      ›
                    </span>
                  </summary>
                  <ToolAttemptBlocks
                    results={toolItem.results}
                    toolName={toolNm}
                    toolArgs={resolvedArgs}
                  />
                </details>
              </div>
            </div>
          )
        })}
      </div>
    </li>
  )
}

/** 渲染单步工具/ReAct 卡片：目标、各轮 Thought/Action/结果与状态徽标。 */
export function TaskToolRoundBlock({ events }: TaskToolRoundBlockProps) {
  // 1. 提取标题、起止状态等元数据
  const meta = analyzeStepMeta(events)
  const workspaceRoot = workspaceRootFromStepStart(meta.stepStart)
  // 2. 按序归并为工具轮与终答轮
  const turns = buildReactTurns(events)
  // 3. 终态已知时解析徽标
  const stepBadge =
    meta.endStatus !== ''
      ? resolveStepEndBadge(meta.endStatus, meta.toolOk, meta.hadAnyToolAttempt)
      : null

  return (
    <article className="rounded-r-lg border border-neutral-200 border-l-4 border-l-primary-500/80 bg-white py-3 pl-4 pr-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded bg-neutral-100 px-2 py-0.5 font-mono text-neutral-600">
            #{meta.firstSeq}
          </span>
          <span className="rounded bg-primary-500/10 px-2 py-0.5 font-medium text-primary-800">
            工具与步骤
          </span>
          {stepBadge ? (
            <span
              className={`rounded border px-2 py-0.5 font-medium ${stepBadge.badgeClass}`}
              title={stepBadge.hint ?? undefined}
            >
              {stepBadge.label}
            </span>
          ) : (
            <span className="rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-900">
              进行中
            </span>
          )}
        </div>
        <time className="shrink-0 font-mono text-xs text-neutral-500">
          {formatDateTime(meta.ts)}
        </time>
      </div>

      <div className="mt-3 space-y-3 text-sm">
        <div className="fa-chat-block-thinking !p-0">
          <details className="fa-thinking-fold" open>
            <summary className="fa-thinking-summary">
              <span className="fa-chat-fold-link">本步目标</span>
              <span className="fa-chat-fold-chevron" aria-hidden>
                ›
              </span>
            </summary>
            <p className="text-neutral-700 text-sm leading-relaxed">{meta.title}</p>
          </details>
        </div>

        {turns.length > 0 ? (
          <ol className="list-decimal space-y-4 pl-5 text-neutral-800 marker:font-medium">
            {turns.map((t) =>
              t.kind === 'tool' ? (
                <ToolRoundListItem
                  key={`tool-${t.round}`}
                  turn={t}
                  workspaceRoot={workspaceRoot}
                />
              ) : (
                <li key={`final-${t.seq}`} className="space-y-2">
                  <div className="fa-chat-block-thinking !p-0">
                    <details className="fa-thinking-fold" open>
                      <summary className="fa-thinking-summary">
                        <span className="fa-chat-fold-link">Thought</span>
                        <span className="fa-chat-fold-chevron" aria-hidden>
                          ›
                        </span>
                      </summary>
                      {t.thought ? (
                        <pre className="fa-chat-thinking-pre mt-1">{t.thought}</pre>
                      ) : (
                        <p className="mt-1 text-neutral-500 text-xs">（无）</p>
                      )}
                    </details>
                  </div>
                  {t.isCompleted ? (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-emerald-800 text-sm">
                      ✓ 步骤已完成
                    </div>
                  ) : t.finalAnswer ? (
                    <div className="max-h-[min(20rem,45vh)] overflow-auto rounded-lg bg-neutral-50/80 px-3 py-2 text-neutral-800 text-sm leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
                      {t.finalAnswer}
                    </div>
                  ) : null}
                </li>
              ),
            )}
          </ol>
        ) : (
          <div className="rounded border border-amber-200 bg-amber-50/40 px-3 py-2 text-amber-950 text-xs leading-relaxed">
            本段尚无 tool_call / react_turn 结构化事件。
            {(meta.headerThought || meta.rawExcerpt) && (
              <div className="mt-2 space-y-2 border-amber-200/80 border-t pt-2">
                {meta.headerThought ? (
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs">
                    {meta.headerThought}
                  </pre>
                ) : null}
                {meta.rawExcerpt ? (
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs text-neutral-800">
                    {meta.rawExcerpt}
                  </pre>
                ) : null}
              </div>
            )}
          </div>
        )}

        {stepBadge?.hint ? (
          <p className="text-amber-900/90 text-xs leading-relaxed">{stepBadge.hint}</p>
        ) : null}
      </div>
    </article>
  )
}
