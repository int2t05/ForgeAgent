/**
 * 会话管理 Hook：自动创建会话并缓存 session_id。
 * 首次进入应用时若无有效 session_id，自动调用后端创建。
 */

import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createSession } from '@/api/sessions'
import { useSessionStore } from '@/stores/sessionStore'

export function useSession() {
  const sessionId = useSessionStore((s) => s.sessionId)
  const setSessionId = useSessionStore((s) => s.setSessionId)

  // 仅在没有有效 session_id 时触发创建
  const { data, isLoading, error } = useQuery({
    queryKey: ['session', 'create'],
    queryFn: () => createSession(),
    enabled: !sessionId,
    staleTime: Infinity,
    retry: 2,
  })

  // 创建成功后写入 store
  useEffect(() => {
    if (data?.session_id && !sessionId) {
      setSessionId(data.session_id)
    }
  }, [data, sessionId, setSessionId])

  return {
    sessionId,
    isLoading: !sessionId && isLoading,
    error,
  }
}
