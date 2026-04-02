/**
 * 单步 / 单轮工具执行块：思考过程、执行计划（工具入参）、可折叠的工具输出。
 */

import { formatDateTime } from '@/utils/format'
import type { TaskEvent } from '@/types/task'

export interface TaskToolRoundBlockProps {
  events: TaskEvent[]
}

function pickPayloadString(p: Record<string, unknown> | null, key: string): string {
  if (!p) return ''
  const v = p[key]
  return typeof v === 'string' ? v : ''
}

function formatJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

/** 工具 result 字段：字符串且含真实换行或字面量 \\n 时用等宽块展示为多行。 */
function formatToolResultBody(data: unknown): { text: string; preWrap: boolean } {
  if (data === null || data === undefined) {
    return { text: formatJson(data), preWrap: false }
  }
  if (typeof data === 'string') {
    if (data.includes('\n') || data.includes('\\n')) {
      const normalized = data.includes('\n')
        ? data
        : data.replace(/\\n/g, '\n')
      return { text: normalized, preWrap: true }
    }
    return { text: data, preWrap: false }
  }
  return { text: formatJson(data), preWrap: false }
}

/** 从一组事件中解析 step_start、最后一次 tool_call/tool_result、step_end。 */
function analyzeRound(events: TaskEvent[]) {
  const stepStart = events.find((e) => e.kind === 'step_start')
  const toolCalls = events.filter((e) => e.kind === 'tool_call')
  const toolResults = events.filter((e) => e.kind === 'tool_result')
  const toolCall = toolCalls.length ? toolCalls[toolCalls.length - 1] : undefined
  const toolResult = toolResults.length ? toolResults[toolResults.length - 1] : undefined
  const stepEnd = events.find((e) => e.kind === 'step_end')
  const title =
    pickPayloadString(stepStart?.payload ?? null, 'title').trim() || '本步执行'
  const thought = pickPayloadString(stepStart?.payload ?? null, 'thought').trim()
  const toolName =
    typeof toolCall?.payload?.tool === 'string' ? toolCall.payload.tool : ''
  const args = toolCall?.payload?.args
  const endStatus =
    typeof stepEnd?.payload?.status === 'string' ? stepEnd.payload.status : ''
  const rawExcerpt =
    typeof stepEnd?.payload?.raw_excerpt === 'string'
      ? stepEnd.payload.raw_excerpt.trim()
      : ''
  const toolOk = toolResult?.payload?.ok === true
  const resultData = toolResult?.payload?.result
  const resultErr = toolResult?.payload?.error
  const hadAnyToolAttempt = toolResults.length > 0
  const firstSeq = events.reduce((m, e) => Math.min(m, e.seq), events[0]?.seq ?? 0)
  const ts = stepStart?.ts ?? events[0]?.ts ?? ''
  return {
    stepStart,
    toolCall,
    toolResult,
    stepEnd,
    title,
    toolName,
    args,
    endStatus,
    toolOk,
    resultData,
    resultErr,
    firstSeq,
    ts,
    thought,
    rawExcerpt,
    hadAnyToolAttempt,
  }
}

/** 步骤级徽标：与后端 step_end.status 对齐，但区分「工具已回报成功但未产出终答」与「硬失败」。 */
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
  if (
    endStatus === 'failed' &&
    hadAnyToolAttempt &&
    toolOk
  ) {
    return {
      label: '未收官',
      badgeClass: 'bg-amber-50 text-amber-900 border-amber-200',
      hint: '工具已返回成功，但本子步未产出有效终答、解析失败或终答审核未通过。',
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

export function TaskToolRoundBlock({ events }: TaskToolRoundBlockProps) {
  const a = analyzeRound(events)

  const hasTool = Boolean(a.toolCall && a.toolName)
  const showResultPanel = Boolean(a.toolResult)
  const stepBadge =
    a.endStatus !== ''
      ? resolveStepEndBadge(a.endStatus, a.toolOk, a.hadAnyToolAttempt)
      : null
  const resultBody = formatToolResultBody(a.resultData ?? null)

  return (
    <article className="rounded-r-lg border border-neutral-200 border-l-4 border-l-primary-500/80 bg-white py-3 pl-4 pr-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded bg-neutral-100 px-2 py-0.5 font-mono text-neutral-600">
            #{a.firstSeq}
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
          {formatDateTime(a.ts)}
        </time>
      </div>

      <div className="mt-3 space-y-3 text-sm">
        {(a.thought || a.rawExcerpt) && (
          <div className="fa-chat-block-thinking !p-0">
            <details className="fa-thinking-fold">
              <summary className="fa-thinking-summary">
                <span className="fa-chat-fold-link">Thought</span>
                <span className="fa-chat-fold-chevron" aria-hidden>
                  ›
                </span>
              </summary>
              {a.thought ? (
                <pre className="fa-chat-thinking-pre">{a.thought}</pre>
              ) : (
                <>
                  <p className="text-neutral-500 text-xs leading-relaxed">
                    未解析到约定字段 <span className="font-mono">thought</span>
                    （或等价的 reasoning / thinking 等）。以下为该轮模型原文节选，便于对照为何被判为{' '}
                    <span className="font-mono">invalid_react_shape</span>：
                  </p>
                  <pre className="fa-chat-thinking-pre mt-2 max-h-[min(24rem,50vh)] overflow-auto">
                    {a.rawExcerpt}
                  </pre>
                </>
              )}
            </details>
          </div>
        )}

        <div className="fa-chat-block-thinking !p-0">
          <details className="fa-thinking-fold">
            <summary className="fa-thinking-summary">
              <span className="fa-chat-fold-link">Step</span>
              <span className="fa-chat-fold-chevron" aria-hidden>
                ›
              </span>
            </summary>
            <p className="text-neutral-700 text-sm leading-relaxed">{a.title}</p>
          </details>
        </div>

        <div className="fa-chat-block-thinking !p-0">
          <details className="fa-thinking-fold">
            <summary className="fa-thinking-summary">
              <span className="fa-chat-fold-link">Action · {hasTool ? a.toolName : '—'}</span>
              <span className="fa-chat-fold-chevron" aria-hidden>
                ›
              </span>
            </summary>
            {hasTool ? (
              <div className="mt-1 space-y-1">
                <p className="font-mono text-neutral-800 text-xs">调用工具：{a.toolName}</p>
                <pre className="max-h-40 overflow-auto rounded-md bg-neutral-900/90 p-2.5 font-mono text-xs text-neutral-100">
                  {formatJson(a.args ?? {})}
                </pre>
              </div>
            ) : (
              <p className="mt-1 text-neutral-600 text-xs leading-relaxed">
                本步未发起工具调用（例如纯推理、或模型未输出有效 action）。
              </p>
            )}
          </details>
        </div>

        {stepBadge?.hint ? (
          <p className="text-amber-900/90 text-xs leading-relaxed">{stepBadge.hint}</p>
        ) : null}

        {showResultPanel && (
          <div className="fa-chat-block-thinking !p-0">
            <details className="fa-thinking-fold">
              <summary className="fa-thinking-summary">
                <span className="fa-chat-fold-link">工具调用结果</span>
                <span className="fa-chat-fold-chevron" aria-hidden>
                  ›
                </span>
              </summary>
              <div className="mt-2 space-y-2">
                <p className="font-mono text-neutral-800 text-xs">
                  <span className="text-neutral-500">状态</span>{' '}
                  <span
                    className={
                      a.toolOk ? 'font-semibold text-emerald-700' : 'font-semibold text-red-700'
                    }
                  >
                    {a.toolOk ? '成功' : '失败'}
                  </span>
                </p>
                {a.resultErr != null && a.resultErr !== '' && (
                  <p className="text-red-800 text-xs leading-relaxed">
                    {typeof a.resultErr === 'string' ? a.resultErr : formatJson(a.resultErr)}
                  </p>
                )}
                <pre
                  className={`max-h-[min(20rem,45vh)] overflow-auto rounded-md bg-neutral-900/90 p-2.5 font-mono text-xs text-neutral-100 ${
                    resultBody.preWrap ? 'whitespace-pre-wrap break-words' : ''
                  }`}
                >
                  {resultBody.text}
                </pre>
              </div>
            </details>
          </div>
        )}
      </div>
    </article>
  )
}
