import { memo, useEffect, useMemo, useState } from 'react'
import { TaskPlanSteps } from '@/components/task/TaskPlanSteps'
import type { PlanStep, PlanTodoProgress } from '@/utils/normalizeTaskPlan'

/** 聊天气泡区顶条：与 ``fa-chat-messages`` 同水平内边距（左缘与消息对齐），可折叠，状态写入 localStorage */
export const ChatHeaderPlanTodos = memo(function ChatHeaderPlanTodos({
  steps,
  todoProgress,
}: {
  steps: PlanStep[]
  todoProgress: PlanTodoProgress
}) {
  const [open, setOpen] = useState(() => {
    if (typeof window === 'undefined') return true
    return window.localStorage.getItem('fa-chat-plan-todos-open') !== '0'
  })

  useEffect(() => {
    window.localStorage.setItem('fa-chat-plan-todos-open', open ? '1' : '0')
  }, [open])

  const { done, total } = useMemo(() => {
    const t = steps.length
    const d = steps.filter((s) => todoProgress.statusByStepId[s.id] === 'done').length
    return { done: d, total: t }
  }, [steps, todoProgress])

  return (
    <div
      className="shrink-0 border-neutral-200/70 border-b bg-white/95 px-3 pb-1 pt-1 sm:px-5"
      aria-label="当前任务步骤"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full min-w-0 items-center gap-2 rounded-md py-0.5 text-left text-neutral-700 transition hover:bg-neutral-100/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500/35"
        aria-expanded={open}
      >
        <span className="font-medium text-[0.6875rem] text-neutral-500 uppercase tracking-wide">
          To-dos
        </span>
        <span className="font-medium text-neutral-400 text-xs tabular-nums">
          {done}/{total}
        </span>
        <span
          className={`ml-auto shrink-0 text-neutral-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          aria-hidden
        >
          <svg
            className="size-4"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M6 9l6 6 6-6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>
      {open ? (
        <div className="mt-0.5 max-h-[min(38vh,10rem)] overflow-y-auto overscroll-contain border-neutral-200/80 border-l pl-2.5">
          <TaskPlanSteps
            steps={steps}
            todoProgress={todoProgress}
            className="border-0 bg-transparent px-0 py-0 shadow-none [font-size:0.8125rem] [--fa-chat-fs:0.8125rem] [--fa-chat-lh:1.45]"
          />
        </div>
      ) : null}
    </div>
  )
})
