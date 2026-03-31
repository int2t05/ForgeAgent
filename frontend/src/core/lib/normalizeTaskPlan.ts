/**
 * 将 API / 事件 payload 中的 plan 结构规范为步骤列表（与后端 plan_created payload 对齐）。
 */

import type { TaskEvent } from '@/modules/tasks/types/task'

export interface PlanStep {
  id: string
  title: string
}

/** 从任意对象解析 steps；至少 1 步且每步需有非空 title。 */
export function normalizePlanStepsFromUnknown(data: unknown): PlanStep[] | null {
  if (data == null || typeof data !== 'object') return null
  const steps = (data as Record<string, unknown>).steps
  if (!Array.isArray(steps) || steps.length === 0) return null
  const out: PlanStep[] = []
  for (let i = 0; i < steps.length; i++) {
    const item = steps[i]
    if (item == null || typeof item !== 'object') return null
    const o = item as Record<string, unknown>
    const id = String(o.id ?? String(i + 1))
    const title = o.title
    if (typeof title !== 'string' || !title.trim()) return null
    out.push({ id, title: title.trim() })
  }
  return out
}

/** 从事件序列中取最近一次 plan_created 的步骤（与详情 API 补充，用于执行初期尚未 refetch 时）。 */
export function latestPlanStepsFromEvents(events: TaskEvent[]): PlanStep[] | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]!
    if (e.kind !== 'plan_created' || !e.payload) continue
    const parsed = normalizePlanStepsFromUnknown(e.payload)
    if (parsed?.length) return parsed
  }
  return null
}
