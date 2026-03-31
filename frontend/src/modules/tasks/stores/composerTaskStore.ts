/**
 * 对话页「当前任务」的客户端状态：pending 任务 id、SSE 聚合出的事件列表、按会话缓存的规划等。
 */
import { create } from 'zustand'
import { latestPlanStepsFromEvents } from '@/core/lib/normalizeTaskPlan'
import type { PlanStep } from '@/core/lib/normalizeTaskPlan'
import type { TaskEvent } from '@/modules/tasks/types/task'

export type ComposerSsePhase = 'idle' | 'loading' | 'streaming' | 'error'

/** 已结束任务归档的规划，用于新轮对话后仍显示上一轮步骤。 */
export interface ArchivedPlanEntry {
  sessionId: string
  steps: PlanStep[]
}

interface ComposerTaskState {
  pendingTaskId: string | null
  pendingSessionId: string | null
  liveTaskEvents: TaskEvent[]
  /** 每会话最近一次从任务事件中得到的规划步骤；任务结束后仍保留以便对话页展示。 */
  stickyPlansBySession: Record<string, PlanStep[]>
  /** 按任务 id 归档的规划（会话内多轮对话各占一条，避免仅保留最后一轮）。 */
  plansByTaskId: Record<string, ArchivedPlanEntry>
  ssePhase: ComposerSsePhase
  sseError: string | null
  lastComposerHadLlmStream: boolean
  setPending: (taskId: string, sessionId: string) => void
  clearPending: () => void
  setLiveEvents: (events: TaskEvent[]) => void
  setSsePhase: (phase: ComposerSsePhase) => void
  setSseError: (msg: string | null) => void
  resetLiveOnly: () => void
  ackComposerStreamFlag: () => void
  clearStickyPlanForSession: (sessionId: string) => void
}

export const useComposerTaskStore = create<ComposerTaskState>()((set) => ({
  pendingTaskId: null,
  pendingSessionId: null,
  liveTaskEvents: [],
  stickyPlansBySession: {},
  plansByTaskId: {},
  ssePhase: 'idle',
  sseError: null,
  lastComposerHadLlmStream: false,
  setPending: (taskId, sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...restSticky } = state.stickyPlansBySession
      return {
        pendingTaskId: taskId,
        pendingSessionId: sessionId,
        liveTaskEvents: [],
        stickyPlansBySession: restSticky,
        ssePhase: 'idle',
        sseError: null,
        lastComposerHadLlmStream: false,
      }
    }),
  clearPending: () =>
    set((state) => {
      const tid = state.pendingTaskId
      const sid = state.pendingSessionId
      let nextPlans = state.plansByTaskId
      if (tid && sid) {
        const fromLive = latestPlanStepsFromEvents(state.liveTaskEvents)
        const sticky = state.stickyPlansBySession[sid]
        const steps =
          fromLive?.length ? fromLive : sticky?.length ? sticky : null
        if (steps?.length) {
          nextPlans = {
            ...state.plansByTaskId,
            [tid]: { sessionId: sid, steps },
          }
        }
      }
      return {
        pendingTaskId: null,
        pendingSessionId: null,
        liveTaskEvents: [],
        ssePhase: 'idle',
        sseError: null,
        plansByTaskId: nextPlans,
      }
    }),
  setLiveEvents: (events) =>
    set((state) => {
      const sid = state.pendingSessionId
      let nextSticky = state.stickyPlansBySession
      if (sid) {
        const steps = latestPlanStepsFromEvents(events)
        if (steps?.length) {
          nextSticky = { ...state.stickyPlansBySession, [sid]: steps }
        }
      }
      return { liveTaskEvents: events, stickyPlansBySession: nextSticky }
    }),
  setSsePhase: (phase) => set({ ssePhase: phase }),
  setSseError: (msg) => set({ sseError: msg }),
  resetLiveOnly: () =>
    set({ liveTaskEvents: [], ssePhase: 'idle', sseError: null }),
  ackComposerStreamFlag: () => set({ lastComposerHadLlmStream: false }),
  clearStickyPlanForSession: (sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...restSticky } = state.stickyPlansBySession
      const nextPlans: Record<string, ArchivedPlanEntry> = {
        ...state.plansByTaskId,
      }
      for (const key of Object.keys(nextPlans)) {
        if (nextPlans[key]?.sessionId === sessionId) delete nextPlans[key]
      }
      return { stickyPlansBySession: restSticky, plansByTaskId: nextPlans }
    }),
}))
