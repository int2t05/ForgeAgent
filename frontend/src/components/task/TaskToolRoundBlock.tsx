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

/** 从一组事件中解析 step_start、tool_call、tool_result、step_end。 */
function analyzeRound(events: TaskEvent[]) {
  const stepStart = events.find((e) => e.kind === 'step_start')
  const toolCall = events.find((e) => e.kind === 'tool_call')
  const toolResult = events.find((e) => e.kind === 'tool_result')
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
  }
}

function statusBadgeClass(status: string): string {
  if (status === 'ok' || status === 'final_answer') {
    return 'bg-emerald-50 text-emerald-800 border-emerald-200'
  }
  if (status === 'skipped_no_tool') {
    return 'bg-neutral-100 text-neutral-700 border-neutral-200'
  }
  if (
    status === 'parse_error' ||
    status === 'invalid_react_shape' ||
    status === 'unknown_tool'
  ) {
    return 'bg-amber-50 text-amber-900 border-amber-200'
  }
  return 'bg-red-50 text-red-800 border-red-200'
}

export function TaskToolRoundBlock({ events }: TaskToolRoundBlockProps) {
  const a = analyzeRound(events)

  const hasTool = Boolean(a.toolCall && a.toolName)
  const showResultPanel = Boolean(a.toolResult)

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
          {a.endStatus ? (
            <span
              className={`rounded border px-2 py-0.5 font-medium ${statusBadgeClass(a.endStatus)}`}
            >
              {a.endStatus}
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
                <pre className="max-h-[min(20rem,45vh)] overflow-auto rounded-md bg-neutral-900/90 p-2.5 font-mono text-xs text-neutral-100">
                  {formatJson(a.resultData ?? null)}
                </pre>
              </div>
            </details>
          </div>
        )}
      </div>
    </article>
  )
}
