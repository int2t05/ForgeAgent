/**
 * React Router 路由表定义（与 PAGES.md 路由对齐）。
 * 所有业务路由共享 AppLayout（侧边栏 + 主内容区）。
 */

import { createBrowserRouter, Navigate } from 'react-router'
import { AppLayout } from '@/components/layout/AppLayout'
import { HomePage } from '@/pages/HomePage'
import { ChatPage } from '@/pages/ChatPage'
import { TaskListPage } from '@/pages/TaskListPage'
import { TaskDetailPage } from '@/pages/TaskDetailPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: 'overview', element: <HomePage /> },
      { path: 'chat', element: <Navigate to="/" replace /> },
      { path: 'tasks', element: <TaskListPage /> },
      { path: 'tasks/:taskId', element: <TaskDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
