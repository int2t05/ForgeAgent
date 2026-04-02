/**
 * 将文本写入剪贴板；用于路径、代码片段等短内容。
 */

import { useState } from 'react'

export interface CopyTextButtonProps {
  text: string
  /** 未复制时按钮文案 */
  label?: string
  className?: string
}

export function CopyTextButton({
  text,
  label = '复制',
  className = '',
}: CopyTextButtonProps) {
  const [done, setDone] = useState(false)
  if (!text.trim()) return null
  return (
    <button
      type="button"
      className={`shrink-0 rounded border border-neutral-200 bg-white px-2 py-0.5 font-medium text-neutral-600 text-xs hover:bg-neutral-50 ${className}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setDone(true)
          window.setTimeout(() => setDone(false), 1200)
        } catch {
          /* 浏览器权限等失败时静默 */
        }
      }}
    >
      {done ? '已复制' : label}
    </button>
  )
}
