/**
 * 任务完成通知 Hook：监听任务状态变化，在任务完成时触发 Toast 通知和系统通知（任务栏闪烁）。
 */
import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useToastStore } from '@/store/toastStore'
import { useComposerTaskStore } from '@/store/composerTaskStore'
import { getTask } from '@/api/tasks'
import { TERMINAL_STATUSES } from '@/constants/task'
import type { TaskStatus } from '@/types/task'

const TASK_STATUS_POLL_INTERVAL_MS = 2000

export function useTaskCompletionNotification() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const pendingTaskId = useComposerTaskStore((s) => s.pendingTaskId)
  const pendingSessionId = useComposerTaskStore((s) => s.pendingSessionId)
  const hasNotifiedRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!pendingTaskId) {
      hasNotifiedRef.current = false
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
      return
    }

    if (hasNotifiedRef.current) return

    const taskId = pendingTaskId

    async function checkTaskStatus() {
      try {
        const task = await queryClient.fetchQuery({
          queryKey: ['task', taskId, 'status-check'],
          queryFn: () => getTask(taskId),
          staleTime: 0,
        })

        if (!TERMINAL_STATUSES.has(task.status)) return

        hasNotifiedRef.current = true
        if (pollTimerRef.current) {
          clearInterval(pollTimerRef.current)
          pollTimerRef.current = null
        }

        const statusMessages: Record<TaskStatus, { title: string; type: 'success' | 'error' | 'info' }> = {
          success: { title: '任务已完成', type: 'success' },
          failed: { title: '任务执行失败', type: 'error' },
          cancelled: { title: '任务已取消', type: 'info' },
          pending: { title: '任务等待中', type: 'info' },
          running: { title: '任务执行中', type: 'info' },
        }

        const message = statusMessages[task.status]

        addToast({
          type: message.type,
          title: message.title,
          description: task.summary || undefined,
          duration: 6000,
        })

        if (task.status === 'success' || task.status === 'failed') {
          if ('Notification' in window && Notification.permission === 'granted') {
            const notification = new Notification(message.title, {
              body: task.summary || (task.status === 'success' ? '您的任务已成功完成' : '任务执行过程中出现错误'),
              icon: '/favicon.ico',
              tag: `task-${taskId}`,
              requireInteraction: false,
            })
            notification.onclick = () => {
              window.focus()
              notification.close()
            }
          }
        }
      } catch (error) {
        console.error('Failed to check task status:', error)
      }
    }

    pollTimerRef.current = setInterval(checkTaskStatus, TASK_STATUS_POLL_INTERVAL_MS)

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [pendingTaskId, pendingSessionId, queryClient, addToast])
}
