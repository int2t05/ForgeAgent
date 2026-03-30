/**
 * 应用整体布局：左侧导航 + 右侧主内容区。
 * 作为 React Router 布局路由组件，渲染 <Outlet /> 展示子路由。
 */

import { Outlet } from 'react-router'
import { Sidebar } from '@/components/layout/Sidebar'
import {
  GlobalPendingComposerBanner,
  PendingComposerTaskSync,
} from '@/components/layout/GlobalPendingComposerBanner'

export function AppLayout() {
  return (
    <div className="fa-app-shell flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <PendingComposerTaskSync />
        <GlobalPendingComposerBanner />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
