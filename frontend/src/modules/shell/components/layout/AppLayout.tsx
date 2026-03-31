/**
 * 应用整体布局：左侧导航 + 右侧主内容区。
 * 作为 React Router 布局路由组件，渲染 <Outlet /> 展示子路由。
 */

import { Outlet } from 'react-router'
import { Sidebar } from '@/modules/shell/components/layout/Sidebar'
import { PendingComposerTaskSync } from '@/modules/shell/components/layout/PendingComposerTaskSync'
import { useMainNavSidebarStore } from '@/modules/shell/stores/mainNavSidebarStore'

export function AppLayout() {
  const mainNavOpen = useMainNavSidebarStore((s) => s.open)

  return (
    <div className="fa-app-shell flex h-screen overflow-hidden">
      <div
        className={`shrink-0 transition-[width] duration-200 ease-out ${
          mainNavOpen
            ? 'w-56'
            : 'pointer-events-none m-0 w-0 min-w-0 overflow-hidden border-0 p-0 opacity-0'
        }`}
        aria-hidden={!mainNavOpen}
      >
        <Sidebar />
      </div>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <PendingComposerTaskSync />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
