/**
 * 对话页：展示会话消息列表，发送用户消息后创建任务并轮询直至助手回复落库。
 */

import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { Header } from '@/components/layout/Header'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ErrorAlert } from '@/components/common/ErrorAlert'
import { useSession } from '@/hooks/useSession'
import { getSessionMessages } from '@/api/sessions'
import { createTask, getTask } from '@/api/tasks'
import type { Message } from '@/types/session'

export function ChatPage() {
  const queryClient = useQueryClient()
  const { sessionId, isLoading: sessionLoading, error: sessionError } = useSession()
  const [draft, setDraft] = useState('')
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null)
  const listEndRef = useRef<HTMLDivElement>(null)

  const messagesQuery = useQuery({
    queryKey: ['session', sessionId, 'messages'],
    queryFn: () => getSessionMessages(sessionId!, { limit: 200 }),
    enabled: Boolean(sessionId),
  })

  const pendingTaskQuery = useQuery({
    queryKey: ['task', pendingTaskId],
    queryFn: () => getTask(pendingTaskId!),
    enabled: Boolean(pendingTaskId),
    refetchInterval: (q) => {
      const st = q.state.data?.status
      return st === 'running' || st === 'pending' ? 400 : false
    },
  })

  useEffect(() => {
    if (!pendingTaskId || !pendingTaskQuery.data) return
    const st = pendingTaskQuery.data.status
    if (st !== 'running' && st !== 'pending') {
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
      setPendingTaskId(null)
    }
  }, [pendingTaskId, pendingTaskQuery.data, queryClient, sessionId])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messagesQuery.data?.messages.length, pendingTaskId])

  const sendMutation = useMutation({
    mutationFn: (text: string) =>
      createTask({ session_id: sessionId!, user_message: text }),
    onSuccess: (res) => {
      setDraft('')
      setPendingTaskId(res.task_id)
      void queryClient.invalidateQueries({ queryKey: ['session', sessionId, 'messages'] })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const t = draft.trim()
    if (!t || !sessionId || sendMutation.isPending || pendingTaskId) return
    sendMutation.mutate(t)
  }

  const messages: Message[] = messagesQuery.data?.messages ?? []
  const busy =
    Boolean(pendingTaskId) &&
    (pendingTaskQuery.data?.status === 'running' ||
      pendingTaskQuery.data?.status === 'pending')

  return (
    <div className="flex flex-1 flex-col">
      <Header title="对话" />

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-6 py-6">
        {sessionLoading && <LoadingSpinner />}

        {sessionError && (
          <ErrorAlert
            message="会话初始化失败"
            detail={
              sessionError instanceof Error ? sessionError.message : '无法创建或恢复会话'
            }
          />
        )}

        {sessionId && (
          <>
            <p className="text-neutral-500 text-sm">
              消息会写入当前会话；执行过程可在{' '}
              <Link to="/tasks" className="fa-link">
                任务
              </Link>{' '}
              中查看计划与事件流。
            </p>

            <div className="fa-card flex min-h-[280px] flex-1 flex-col overflow-hidden p-0">
              <div className="flex-1 space-y-3 overflow-y-auto p-4">
                {messagesQuery.isLoading && <LoadingSpinner />}
                {messagesQuery.error && (
                  <ErrorAlert
                    message="加载消息失败"
                    detail={
                      messagesQuery.error instanceof Error
                        ? messagesQuery.error.message
                        : '未知错误'
                    }
                  />
                )}
                {messages.length === 0 && !messagesQuery.isLoading && (
                  <p className="text-center text-neutral-400 text-sm">暂无消息，在下方输入开始对话</p>
                )}
                {messages.map((m) => (
                  <MessageBubble key={m.id} message={m} />
                ))}
                {busy && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl rounded-bl-md bg-neutral-100 px-4 py-2.5 text-neutral-500 text-sm">
                      正在执行…
                    </div>
                  </div>
                )}
                <div ref={listEndRef} />
              </div>

              <form
                onSubmit={handleSubmit}
                className="border-neutral-100 border-t bg-neutral-50/80 p-4"
              >
                {sendMutation.error && (
                  <ErrorAlert
                    message="发送失败"
                    detail={
                      sendMutation.error instanceof Error
                        ? sendMutation.error.message
                        : '未知错误'
                    }
                  />
                )}
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="输入消息…"
                    rows={2}
                    disabled={busy || sendMutation.isPending}
                    className="fa-input min-h-[80px] flex-1 resize-none"
                  />
                  <button
                    type="submit"
                    disabled={
                      !draft.trim() || busy || sendMutation.isPending || !sessionId
                    }
                    className="fa-btn-primary shrink-0 sm:min-w-[96px]"
                  >
                    {sendMutation.isPending || busy ? '处理中…' : '发送'}
                  </button>
                </div>
              </form>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'rounded-br-md bg-primary-600 text-white'
            : 'rounded-bl-md border border-neutral-200/90 bg-white text-neutral-800'
        }`}
      >
        <span className="mb-1 block text-[10px] uppercase opacity-70 tracking-wide">
          {isUser ? '你' : '助手'}
        </span>
        <pre className="font-sans whitespace-pre-wrap break-words">{message.content}</pre>
      </div>
    </div>
  )
}
