/**
 * 将 API / 事件 payload 中的 plan 结构规范为步骤列表（与后端 plan_created payload 对齐）。
 */

import type { TaskEvent } from '@/types/task'

export interface PlanStep {
  id: string
  title: string
}

/** 对话区 To-do 与步骤 id 对齐的三种状态。 */
export type PlanStepTodoStatus = 'pending' | 'active' | 'done'

/** 由执行事件推导：react_turn 含非空 final_answer 时该 step_id 记为完成；进行中取最近一次 `step_start` 且尚未终答的步骤。 */
export interface PlanTodoProgress {
  statusByStepId: Record<string, PlanStepTodoStatus>
}

function normStepId(id: string): string {
  return String(id)
}

/** 按 seq 扫描 `step_start` / `react_turn`，供消息区 To-do 与后端 ReAct 终答对齐。 */
export function derivePlanTodoProgress(
  events: TaskEvent[],
  steps: PlanStep[],
): PlanTodoProgress {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const completed = new Set<string>()
  let lastStepStartId: string | null = null

  for (const e of sorted) {
    if (e.kind === 'step_start') {
      const sid = e.payload?.step_id
      if (sid != null && String(sid).trim() !== '') {
        lastStepStartId = String(sid)
      }
    } else if (e.kind === 'react_turn') {
      const p = e.payload
      const fa = p && typeof p.final_answer === 'string' ? p.final_answer.trim() : ''
      const rid = p?.step_id
      if (fa && rid != null && String(rid).trim() !== '') {
        completed.add(String(rid))
      }
    }
  }

  const statusByStepId: Record<string, PlanStepTodoStatus> = {}
  for (const s of steps) {
    const id = normStepId(s.id)
    if (completed.has(id)) {
      statusByStepId[id] = 'done'
    } else if (lastStepStartId != null && id === lastStepStartId) {
      statusByStepId[id] = 'active'
    } else {
      statusByStepId[id] = 'pending'
    }
  }

  return { statusByStepId }
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
