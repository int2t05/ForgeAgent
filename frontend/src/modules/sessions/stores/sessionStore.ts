/**
 * 会话状态管理（Zustand + sessionStorage 持久化）。
 * 仅管理当前 session_id；任务/事件等服务端状态由 TanStack Query 管理。
 */

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface SessionState {
  /** 当前活跃会话 ID（为空表示尚未创建）。 */
  sessionId: string | null
  /** 设置会话 ID。 */
  setSessionId: (id: string) => void
  /** 清除会话（用户主动重置时调用）。 */
  clearSession: () => void
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessionId: null,
      setSessionId: (id: string) => set({ sessionId: id }),
      clearSession: () => set({ sessionId: null }),
    }),
    {
      name: 'forgeagent-session',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ sessionId: state.sessionId }),
    },
  ),
)
