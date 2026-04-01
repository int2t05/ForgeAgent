/**
 * 错误提示组件：可关闭的红色警告条。
 */

import { useState } from 'react'

interface ErrorAlertProps {
  /** 错误主消息。 */
  message: string
  /** 可选详细信息。 */
  detail?: string
  /** 是否允许关闭（默认 true）。 */
  dismissible?: boolean
  /** 关闭按钮被点击后回调（用于同步清空外部状态，如全局 store）。 */
  onDismiss?: () => void
}

export function ErrorAlert({
  message,
  detail,
  dismissible = true,
  onDismiss,
}: ErrorAlertProps) {
  const [visible, setVisible] = useState(true)

  if (!visible) return null

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">{message}</p>
          {detail && <p className="mt-1 text-red-600">{detail}</p>}
        </div>
        {dismissible && (
          <button
            type="button"
            onClick={() => {
              setVisible(false)
              onDismiss?.()
            }}
            className="shrink-0 text-red-400 transition-colors hover:text-red-600"
            aria-label="关闭"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}
