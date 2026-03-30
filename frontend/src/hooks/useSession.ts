/**
 * 会话上下文：当前选中的 session_id（Zustand + sessionStorage）。
 * 会话在对话页通过列表或「新会话」显式创建/选择，不在此自动创建。
 */

import { useSessionStore } from '@/stores/sessionStore'

export function useSession() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const setSessionId = useSessionStore((s) => s.setSessionId)
  const clearSession = useSessionStore((s) => s.clearSession)

  return { sessionId, setSessionId, clearSession }
}
