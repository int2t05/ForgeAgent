/**
 * 全局左侧主导航（AppLayout Sidebar）展开/折叠，供对话页刘海按钮等跨组件控制。
 */
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

interface MainNavSidebarState {
  open: boolean
  setOpen: (open: boolean) => void
  toggle: () => void
}

export const useMainNavSidebarStore = create<MainNavSidebarState>()(
  persist(
    (set) => ({
      open: true,
      setOpen: (open) => set({ open }),
      toggle: () => set((s) => ({ open: !s.open })),
    }),
    {
      name: 'forgeagent-main-nav-open',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ open: s.open }),
    },
  ),
)
