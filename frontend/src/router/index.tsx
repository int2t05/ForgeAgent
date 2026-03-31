/**
 * React Router 路由表定义（与 PAGES.md 路由对齐）。
 * 所有业务路由共享 AppLayout（侧边栏 + 主内容区）。
 * 页面级组件使用 lazy 代码分割，减小首包。
 */

import { lazy } from 'react'
import { createBrowserRouter, Navigate } from 'react-router'
import { AppLayout } from '@/layouts/AppLayout'

const HomePage = lazy(() =>
  import('@/views/HomePage').then((m) => ({ default: m.HomePage })),
)
const ChatPage = lazy(() =>
  import('@/views/ChatPage').then((m) => ({ default: m.ChatPage })),
)
const SessionHistoryPage = lazy(() =>
  import('@/views/SessionHistoryPage').then((m) => ({ default: m.SessionHistoryPage })),
)
const TaskListPage = lazy(() =>
  import('@/views/TaskListPage').then((m) => ({ default: m.TaskListPage })),
)
const TaskDetailPage = lazy(() =>
  import('@/views/TaskDetailPage').then((m) => ({ default: m.TaskDetailPage })),
)
const SettingsPage = lazy(() =>
  import('@/views/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const NotFoundPage = lazy(() =>
  import('@/views/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)

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
