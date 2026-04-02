import { useEffect, useState } from 'react'

const STORAGE_KEY = 'fa-chat-workspace-sidebar'

/** 对话页右侧工作区侧栏显隐，读写 ``localStorage`` 以保持刷新后状态。 */
export function useWorkspaceSidebarOpen() {
  const [open, setOpen] = useState(() => {
    if (typeof window === 'undefined') return true
    return window.localStorage.getItem(STORAGE_KEY) !== '0'
  })

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, open ? '1' : '0')
  }, [open])

  return [open, setOpen] as const
}
