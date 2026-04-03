import {
  ChatHeaderNavToggleIcon,
  ChatHeaderNewSessionIcon,
  ChatHeaderWorkspaceIcon,
} from '@/components/chat/ChatPageIcons'

export interface ChatPageHeaderBarProps {
  mainNavOpen: boolean
  onToggleMainNav: () => void
  onNewSession: () => void
  newSessionPending: boolean
  sessionId: string | null
  workspaceSidebarOpen: boolean
  onToggleWorkspaceSidebar: () => void
  sessionTitle: string | null | undefined
}

/** 对话页顶栏：主导航 / 新会话 / 工作区侧栏 + 居中标题区 */
export function ChatPageHeaderBar({
  mainNavOpen,
  onToggleMainNav,
  onNewSession,
  newSessionPending,
  sessionId,
  workspaceSidebarOpen,
  onToggleWorkspaceSidebar,
  sessionTitle,
}: ChatPageHeaderBarProps) {
  return (
    <div className="mb-0.5 shrink-0 border-neutral-200/80 border-b bg-white/90 px-2 py-0.5 sm:px-3 sm:py-1">
      <div className="flex items-center gap-1 sm:gap-1.5">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <div className="flex shrink-0 items-center gap-0.5">
            <button
              type="button"
              onClick={onToggleMainNav}
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
              aria-label={mainNavOpen ? '隐藏导航栏' : '显示导航栏'}
              aria-expanded={mainNavOpen}
            >
              <ChatHeaderNavToggleIcon className="size-5" />
            </button>
            <button
              type="button"
              onClick={onNewSession}
              disabled={newSessionPending}
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35 disabled:cursor-not-allowed disabled:opacity-45"
              aria-label="新会话"
            >
              <ChatHeaderNewSessionIcon className="size-5" />
            </button>
            {sessionId ? (
              <button
                type="button"
                onClick={onToggleWorkspaceSidebar}
                aria-pressed={workspaceSidebarOpen}
                aria-label={workspaceSidebarOpen ? '隐藏工作区侧栏' : '显示工作区侧栏'}
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
              >
                <ChatHeaderWorkspaceIcon className="size-5" />
              </button>
            ) : null}
          </div>
          <div className="min-w-0 flex-1 self-center">
            {sessionId ? (
              <p className="truncate font-medium text-sm text-neutral-900">
                {sessionTitle?.trim() || '新对话'}
              </p>
            ) : (
              <p className="truncate font-medium text-sm text-neutral-800">对话</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
