/**
 * 单条任务事件行：模块与 kind 标签、错误高亮、payload 摘要与展开全文。
 */

import { useId, useState } from 'react'
import { formatDateTime } from '@/utils/format'
import type { TaskEvent } from '@/types/task'

const MODULE_LABEL: Record<string, string> = {
  planning: '规划',
  memory: '记忆',
  tool: '工具',
  execution: '执行',
}

const KIND_LABEL: Record<string, string> = {
  plan_created: '计划已生成',
  step_start: '步骤开始',
  step_end: '步骤结束',
  tool_call: '工具调用',
  tool_result: '工具结果',
  error: '错误',
  replan: '重规划',
  llm_stream_delta: '流式输出',
}

function moduleLabel(m: string): string {
  return MODULE_LABEL[m] ?? m
}

function kindLabel(k: string): string {
  return KIND_LABEL[k] ?? k
}

function payloadPreview(payload: Record<string, unknown> | null): string {
  if (!payload || Object.keys(payload).length === 0) {
    return '（无附加数据）'
  }
  try {
    const s = JSON.stringify(payload)
    if (s.length <= 160) {
      return s
    }
    return `${s.slice(0, 157)}…`
  } catch {
    return '（无法序列化）'
  }
}

export interface TaskEventRowProps {
  event: TaskEvent
}

export function TaskEventRow({ event }: TaskEventRowProps) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const isError = event.kind === 'error'
  const isReplan = event.kind === 'replan'

  const borderAccent = isError
    ? 'border-l-red-500 bg-red-50/40'
    : isReplan
      ? 'border-l-amber-500 bg-amber-50/30'
      : 'border-l-primary-500/70 bg-white'

  return (
    <article
      className={`rounded-r-lg border border-neutral-200 border-l-4 py-3 pl-4 pr-3 ${borderAccent}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded bg-neutral-100 px-2 py-0.5 font-mono text-neutral-600">
            #{event.seq}
          </span>
          <span className="rounded bg-neutral-100 px-2 py-0.5 text-neutral-700">
            {moduleLabel(event.module)}
          </span>
          <span
            className={`rounded px-2 py-0.5 font-medium ${
              isError ? 'bg-red-100 text-red-800' : 'bg-neutral-200/80 text-neutral-800'
            }`}
          >
            {kindLabel(event.kind)}
          </span>
        </div>
        <time className="shrink-0 font-mono text-xs text-neutral-500">
          {formatDateTime(event.ts)}
        </time>
      </div>

      {open ? (
        <pre
          id={panelId}
          className="mt-2 max-h-64 overflow-auto rounded-md bg-neutral-900/90 p-3 font-mono text-xs text-neutral-100"
        >
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      ) : (
        <p className="mt-2 font-mono text-xs text-neutral-600 break-all">
          {payloadPreview(event.payload)}
        </p>
      )}

      {event.payload && Object.keys(event.payload).length > 0 && (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="fa-link mt-2 text-xs"
        >
          {open ? '收起全文' : '展开全文'}
        </button>
      )}
    </article>
  )
}
