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
    <div className="mb-1 shrink-0 border-neutral-200/80 border-b bg-white/90 px-2 py-1.5 sm:px-3 sm:py-2">
      <div className="flex items-center gap-1.5 sm:gap-2">
        <div className="flex shrink-0 items-center gap-1.5 self-center">
          <button
            type="button"
            onClick={onToggleMainNav}
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
            aria-label={mainNavOpen ? '隐藏导航栏' : '显示导航栏'}
            aria-expanded={mainNavOpen}
          >
            <ChatHeaderNavToggleIcon className="size-[1.375rem]" />
          </button>
          <button
            type="button"
            onClick={onNewSession}
            disabled={newSessionPending}
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35 disabled:cursor-not-allowed disabled:opacity-45"
            aria-label="新会话"
          >
            <ChatHeaderNewSessionIcon className="size-[1.375rem]" />
          </button>
          {sessionId ? (
            <button
              type="button"
              onClick={onToggleWorkspaceSidebar}
              aria-pressed={workspaceSidebarOpen}
              aria-label={workspaceSidebarOpen ? '隐藏工作区侧栏' : '显示工作区侧栏'}
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-neutral-900 transition hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
            >
              <ChatHeaderWorkspaceIcon className="size-[1.375rem]" />
            </button>
          ) : null}
        </div>
        <div className="min-w-0 flex-1 self-center text-center">
          {sessionId ? (
            <>
              <p className="truncate font-medium text-base text-neutral-900">
                {sessionTitle?.trim() || '新对话'}
              </p>
              <p className="fa-text-caption text-neutral-500">内容由 AI 生成，请核对重要信息</p>
            </>
          ) : (
            <>
              <p className="truncate font-medium text-base text-neutral-800">对话</p>
              <p className="fa-text-caption text-neutral-500">
                在左侧边栏「历史对话」中选会话，或点击「新会话」。
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
