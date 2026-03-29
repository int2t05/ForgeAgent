/**
 * 任务事件 SSE：流式 URL 与 fetch + ReadableStream 消费（阶段7）。
 * 使用 fetch 而非 EventSource，以便统一携带 `after_seq` 并接收任意 `event:` 类型。
 */

import { API_BASE_URL } from '@/lib/constants'
import { parseSseDataJson, splitSseBlocks } from '@/lib/sseParse'
import type { TaskEvent } from '@/types/task'

/**
 * 构建 GET .../events/stream 完整 URL。
 */
export function buildTaskEventsStreamUrl(taskId: string, afterSeq: number): string {
  const base = API_BASE_URL.replace(/\/+$/, '')
  const u = new URL(`${base}/api/v1/tasks/${encodeURIComponent(taskId)}/events/stream`)
  u.searchParams.set('after_seq', String(afterSeq))
  return u.toString()
}

/**
 * 将 JSON 对象规范为 TaskEvent（运行时再校验字段）。
 */
function asTaskEvent(raw: unknown): TaskEvent | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const o = raw as Record<string, unknown>
  if (typeof o.seq !== 'number') {
    return null
  }
  return {
    seq: o.seq,
    ts: typeof o.ts === 'string' ? o.ts : String(o.ts ?? ''),
    module: (typeof o.module === 'string' ? o.module : 'execution') as TaskEvent['module'],
    kind: (typeof o.kind === 'string' ? o.kind : 'unknown') as TaskEvent['kind'],
    payload:
      o.payload != null && typeof o.payload === 'object'
        ? (o.payload as Record<string, unknown>)
        : null,
  }
}

function parseBlocksToEvents(blocks: string[]): TaskEvent[] {
  const out: TaskEvent[] = []
  for (const block of blocks) {
    const jsonStr = parseSseDataJson(block)
    if (!jsonStr) {
      continue
    }
    try {
      const parsed: unknown = JSON.parse(jsonStr)
      const ev = asTaskEvent(parsed)
      if (ev) {
        out.push(ev)
      }
    } catch {
      /* 跳过非法 JSON 帧 */
    }
  }
  return out
}

/**
 * 读取 SSE 流直至连接结束；对每条 `data:` JSON 调用 onEvent。
 */
export async function consumeTaskEventStream(
  url: string,
  signal: AbortSignal,
  onEvent: (event: TaskEvent) => void,
): Promise<void> {
  const res = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!res.ok) {
    let detail = res.statusText || 'SSE 请求失败'
    try {
      const j = (await res.json()) as { detail?: string }
      if (typeof j.detail === 'string') {
        detail = j.detail
      }
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new Error(detail)
  }
  const body = res.body
  if (!body) {
    throw new Error('响应体不可读')
  }

  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (value) {
        buffer += decoder.decode(value, { stream: true })
      }
      const split = splitSseBlocks(buffer)
      buffer = split.rest
      for (const ev of parseBlocksToEvents(split.blocks)) {
        onEvent(ev)
      }
      if (done) {
        buffer += decoder.decode()
        const final = splitSseBlocks(buffer)
        for (const ev of parseBlocksToEvents(final.blocks)) {
          onEvent(ev)
        }
        break
      }
    }
  } finally {
    reader.releaseLock()
  }
}
