/**
 * 对话页「当前任务」的客户端状态：pending 任务 id、SSE 聚合出的事件列表、按会话缓存的规划等。
 */
import { create } from 'zustand'
import {
  derivePlanTodoProgress,
  latestPlanStepsFromEvents,
} from '@/utils/normalizeTaskPlan'
import type { PlanStep, PlanTodoProgress } from '@/utils/normalizeTaskPlan'
import type { TaskEvent } from '@/types/task'
import {
  composerRoundsHaveContent,
  foldComposerLlmStreamForFreeze,
  type ComposerRoundSegment,
} from '@/utils/foldComposerLlmStream'

/** 任务结束后保留在对话区的思考/行动快照（避免被清空后再也看不到） */
export interface ComposerStreamFreeze {
  taskId: string
  sessionId: string
  rounds: ComposerRoundSegment[]
}

export type ComposerSsePhase = 'idle' | 'loading' | 'streaming' | 'error'

/** 已结束任务归档的规划，用于新轮对话后仍显示上一轮步骤。 */
export interface ArchivedPlanEntry {
  sessionId: string
  steps: PlanStep[]
  /** 任务结束时由 live 事件推导，避免仅内存态丢失 To-do 勾选 */
  todoProgress?: PlanTodoProgress
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
  /** 上一轮流式思考/行动归档；新任务 setPending 时清空 */
  composerStreamFreeze: ComposerStreamFreeze | null
  setPending: (taskId: string, sessionId: string) => void
  /**
   * @param opts.keepSseError 为 true 时保留 {@link sseError}（用于拉事件/SSE 失败时仍能提示用户）。
   */
  clearPending: (opts?: { keepSseError?: boolean }) => void
  setLiveEvents: (events: TaskEvent[]) => void
  setSsePhase: (phase: ComposerSsePhase) => void
  setSseError: (msg: string | null) => void
  /** 关闭对话区顶栏中与事件流相关的错误提示 */
  ackSseError: () => void
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
  composerStreamFreeze: null,
  setPending: (taskId, sessionId) =>
    set((state) => ({
      pendingTaskId: taskId,
      pendingSessionId: sessionId,
      liveTaskEvents: [],
      ssePhase: 'idle',
      sseError: null,
      lastComposerHadLlmStream: false,
      detachedComposerPlan: null,
      composerStreamFreeze: null,
    })),
  clearPending: (opts) =>
    set((state) => {
      const keepErr = Boolean(opts?.keepSseError)
      const tid = state.pendingTaskId
      const sid = state.pendingSessionId
      const events = state.liveTaskEvents
      let composerStreamFreeze: ComposerStreamFreeze | null = null
      if (tid && sid && events.length > 0) {
        const frozen = foldComposerLlmStreamForFreeze(events)
        if (composerRoundsHaveContent(frozen.rounds)) {
          composerStreamFreeze = {
            taskId: tid,
            sessionId: sid,
            rounds: frozen.rounds,
          }
        }
      }
      let nextPlans = state.plansByTaskId
      if (tid && sid) {
        const fromLive = latestPlanStepsFromEvents(state.liveTaskEvents)
        const sticky = state.stickyPlansBySession[sid]
        const steps =
          fromLive?.length ? fromLive : sticky?.length ? sticky : null
        if (steps?.length) {
          const todoProgress = derivePlanTodoProgress(state.liveTaskEvents, steps)
          nextPlans = {
            ...state.plansByTaskId,
            [tid]: { sessionId: sid, steps, todoProgress },
          }
        }
      }
      return {
        pendingTaskId: null,
        pendingSessionId: null,
        liveTaskEvents: [],
        ssePhase: keepErr ? 'error' : 'idle',
        sseError: keepErr ? state.sseError : null,
        plansByTaskId: nextPlans,
        composerStreamFreeze,
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
  ackSseError: () => set({ sseError: null, ssePhase: 'idle' }),
  resetLiveOnly: () =>
    set({ liveTaskEvents: [], ssePhase: 'idle', sseError: null }),
  ackComposerStreamFlag: () => set({ lastComposerHadLlmStream: false }),
  clearStickyPlanForSession: (sessionId) =>
    set((state) => {
      const restSticky = { ...state.stickyPlansBySession }
      delete restSticky[sessionId]
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
