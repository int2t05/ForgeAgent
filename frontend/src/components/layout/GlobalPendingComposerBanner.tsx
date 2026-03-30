import { Link, useLocation } from 'react-router'
import {
  usePendingComposerTaskBusy,
  usePendingComposerTaskMeta,
  usePendingComposerTaskSync,
} from '@/hooks/usePendingComposerTask'
import { useSessionStore } from '@/stores/sessionStore'

export function GlobalPendingComposerBanner() {
  const location = useLocation()
  const busy = usePendingComposerTaskBusy()
  const { pendingTaskId, pendingSessionId } = usePendingComposerTaskMeta()
  const sessionId = useSessionStore((s) => s.sessionId)

  if (!busy || !pendingTaskId) return null

  const onChatSameSession =
    location.pathname === '/' && sessionId === pendingSessionId

  if (onChatSameSession) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="shrink-0 border-amber-200/90 border-b bg-amber-50 px-4 py-2.5 text-amber-950 text-sm"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2">
        <span className="inline-flex items-center gap-2 font-medium">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-50" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
          </span>
          有回复生成中
        </span>
        <div className="flex flex-wrap gap-3 text-xs font-medium">
          <Link to="/" className="text-primary-700 underline-offset-2 hover:underline">
            返回对话
          </Link>
          <Link
            to={`/tasks/${pendingTaskId}`}
            className="text-primary-700 underline-offset-2 hover:underline"
          >
            查看任务
          </Link>
        </div>
      </div>
    </div>
  )
}

export function PendingComposerTaskSync() {
  usePendingComposerTaskSync()
  return null
}
