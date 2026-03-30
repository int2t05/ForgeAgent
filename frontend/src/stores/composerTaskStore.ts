import { create } from 'zustand'
import { latestPlanStepsFromEvents } from '@/lib/normalizeTaskPlan'
import type { PlanStep } from '@/lib/normalizeTaskPlan'
import type { TaskEvent } from '@/types/task'

export type ComposerSsePhase = 'idle' | 'loading' | 'streaming' | 'error'

interface ComposerTaskState {
  pendingTaskId: string | null
  pendingSessionId: string | null
  liveTaskEvents: TaskEvent[]
  /** 每会话最近一次从任务事件中得到的规划步骤；任务结束后仍保留以便对话页展示。 */
  stickyPlansBySession: Record<string, PlanStep[]>
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
    set({
      pendingTaskId: null,
      pendingSessionId: null,
      liveTaskEvents: [],
      ssePhase: 'idle',
      sseError: null,
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
      const { [sessionId]: _, ...rest } = state.stickyPlansBySession
      return { stickyPlansBySession: rest }
    }),
}))
