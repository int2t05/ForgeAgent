/** SVG icons used only by the chat page header and composer controls. */

/** 顶栏：隐藏/显示最左侧主导航（圆角方壳 + 左侧约 1/3 处竖线，与常见侧栏抽屉图标一致） */
export function ChatHeaderNavToggleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="4"
        y="5"
        width="16"
        height="14"
        rx="3"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M9 7.5v9"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** 顶栏：切换右侧工作区侧栏（与对话区并排） */
export function ChatHeaderWorkspaceIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="3.25"
        y="4.75"
        width="17.5"
        height="14.5"
        rx="2.25"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M9.25 4.75v14.5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** 顶栏：新会话（方壳内铅笔，与导航按钮同风格） */
export function ChatHeaderNewSessionIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="4"
        y="4"
        width="16"
        height="16"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M12.25 16.25h5.25M15 7a1.9 1.9 0 012.7 2.7l-7 7-2.75.55.55-2.75 7-7z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** 圆形发送钮内向上箭头（界面不出现「发送」字样，依赖 `aria-label`） */
export function ChatSendArrowIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M12 19V8m0 0-3.5 3.5M12 8l3.5 3.5"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** 生成中：圆钮内的「停止」方块（与常见对话产品一致） */
export function ChatStopIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect x="8" y="8" width="8" height="8" rx="2" fill="currentColor" />
    </svg>
  )
}
