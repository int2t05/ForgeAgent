/**
 * 对话页「当前任务」的客户端状态：pending 任务 id、SSE 聚合出的事件列表、按会话缓存的规划等。
 */
import { create } from 'zustand'
import { latestPlanStepsFromEvents } from '@/utils/normalizeTaskPlan'
import type { PlanStep } from '@/utils/normalizeTaskPlan'
import type { TaskEvent } from '@/types/task'

export type ComposerSsePhase = 'idle' | 'loading' | 'streaming' | 'error'

/** 已结束任务归档的规划，用于新轮对话后仍显示上一轮步骤。 */
export interface ArchivedPlanEntry {
  sessionId: string
  steps: PlanStep[]
}

/**
 * 用户停止且本轮用户消息被后端回滚删除时，消息列里不再挂载该用户气泡，
 * 规划需临时挂在输入区上方直到用户再次发送。
 */
export interface DetachedComposerPlan {
  sessionId: string
  taskId: string
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
  /** 停止+回滚用户消息后，与会话底栏关联的「孤立」规划展示。 */
  detachedComposerPlan: DetachedComposerPlan | null
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
  setDetachedComposerPlan: (v: DetachedComposerPlan | null) => void
  clearDetachedComposerPlan: () => void
}

export const useComposerTaskStore = create<ComposerTaskState>()((set) => ({
  pendingTaskId: null,
  pendingSessionId: null,
  liveTaskEvents: [],
  stickyPlansBySession: {},
  plansByTaskId: {},
  detachedComposerPlan: null,
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
        detachedComposerPlan: null,
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
      const nextDetached =
        state.detachedComposerPlan?.sessionId === sessionId
          ? null
          : state.detachedComposerPlan
      return {
        stickyPlansBySession: restSticky,
        plansByTaskId: nextPlans,
        detachedComposerPlan: nextDetached,
      }
    }),
  setDetachedComposerPlan: (v) => set({ detachedComposerPlan: v }),
  clearDetachedComposerPlan: () => set({ detachedComposerPlan: null }),
}))
