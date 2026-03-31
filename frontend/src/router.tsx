/**
 * React Router 路由表定义（与 PAGES.md 路由对齐）。
 * 所有业务路由共享 AppLayout（侧边栏 + 主内容区）。
 */

import { createBrowserRouter, Navigate } from 'react-router'
import { AppLayout } from '@/modules/shell/components/layout/AppLayout'
import { HomePage } from '@/modules/shell/pages/HomePage'
import { ChatPage } from '@/modules/chat/pages/ChatPage'
import { SessionHistoryPage } from '@/modules/chat/pages/SessionHistoryPage'
import { TaskListPage } from '@/modules/tasks/pages/TaskListPage'
import { TaskDetailPage } from '@/modules/tasks/pages/TaskDetailPage'
import { SettingsPage } from '@/modules/settings/pages/SettingsPage'
import { NotFoundPage } from '@/modules/shell/pages/NotFoundPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: 'overview', element: <HomePage /> },
      { path: 'chat', element: <Navigate to="/" replace /> },
      { path: 'chat/history', element: <SessionHistoryPage /> },
      { path: 'tasks', element: <TaskListPage /> },
      { path: 'tasks/:taskId', element: <TaskDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
