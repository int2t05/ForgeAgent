import { useLayoutEffect, useRef } from 'react'
import { isNearScrollBottom } from '@/utils/isNearScrollBottom'

export interface ChatPageMessagesScrollDeps {
  sessionId: string | null
  messagesLoading: boolean
  messagesLen: number
  busy: boolean
  /** 用于生成中随流式块增高时跟滚 */
  streamedRoundsPayloadLen: number
  streamedAnswerLen: number
  archiveRoundsPayloadLen: number
}

/**
 * 消息列表吸底：切换会话强制一次；生成中仅在贴近底部时跟滚。
 */
export function useChatPageMessagesScroll(deps: ChatPageMessagesScrollDeps) {
  const messagesScrollRef = useRef<HTMLDivElement>(null)
  const listEndRef = useRef<HTMLDivElement>(null)
  const forceScrollToLatestRef = useRef(false)
  const prevSessionIdForScrollRef = useRef<string | null | undefined>(undefined)

  useLayoutEffect(() => {
    if (deps.sessionId !== prevSessionIdForScrollRef.current) {
      prevSessionIdForScrollRef.current = deps.sessionId
      forceScrollToLatestRef.current = true
    }

    const root = messagesScrollRef.current
    const end = listEndRef.current
    if (!end || !deps.sessionId) return

    const force = forceScrollToLatestRef.current
    if (force && deps.messagesLoading) {
      return
    }

    if (!force && deps.busy && root && !isNearScrollBottom(root)) {
      return
    }

    end.scrollIntoView({ behavior: 'auto', block: 'end' })
    if (force) {
      forceScrollToLatestRef.current = false
    }
  }, [
    deps.sessionId,
    deps.messagesLoading,
    deps.messagesLen,
    deps.busy,
    deps.streamedRoundsPayloadLen,
    deps.streamedAnswerLen,
    deps.archiveRoundsPayloadLen,
  ])

  return { messagesScrollRef, listEndRef }
}
