import type { PlanStep, PlanTodoProgress } from '@/utils/normalizeTaskPlan'

interface TaskPlanStepsProps {
  steps: PlanStep[]
  className?: string
  /** 传入时渲染消息区 To-do 样式（勾/进行中/待办）；不传则为任务详情等场景的编号列表 */
  todoProgress?: PlanTodoProgress | null
}

function TodoStatusIcon({ status }: { status: 'pending' | 'active' | 'done' }) {
  if (status === 'done') {
    return (
      <svg
        className="size-[1.125rem] shrink-0 text-emerald-600"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <path
          d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
          stroke="currentColor"
          strokeWidth="1.75"
        />
        <path
          d="M8.25 12.25 11 15l4.75-5.5"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }
  if (status === 'active') {
    return (
      <span
        className="fa-chat-send-spinner mt-[0.12em] size-[1.05rem] shrink-0 text-primary-600"
        aria-hidden
      />
    )
  }
  return (
    <svg
      className="mt-[0.1em] size-[1.05rem] shrink-0 text-neutral-300"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.65" />
    </svg>
  )
}

export function TaskPlanSteps({ steps, className = '', todoProgress }: TaskPlanStepsProps) {
  if (!todoProgress) {
    return (
      <ol
        className={`fa-task-plan-steps list-none rounded-lg border border-neutral-200/80 bg-white px-2 py-1.5 shadow-[0_1px_2px_rgb(15_23_42/0.04)] ${className}`.trim()}
      >
        {steps.map((s, index) => (
          <li
            key={`${s.id}-${index}`}
            className="flex items-start gap-1.5 text-neutral-800"
          >
            <span
              className="mt-[0.08em] w-5 shrink-0 tabular-nums text-neutral-400"
              style={{ fontSize: 'calc(var(--fa-chat-fs) * 0.88)' }}
              aria-hidden
            >
              {index + 1}.
            </span>
            <span
              className="min-w-0 flex-1"
              style={{ fontSize: 'var(--fa-chat-fs)', lineHeight: 'var(--fa-chat-lh)' }}
            >
              {s.title}
            </span>
          </li>
        ))}
      </ol>
    )
  }

  const { statusByStepId } = todoProgress

  return (
    <ul
      className={`fa-task-plan-steps fa-task-plan-todos list-none rounded-lg border border-neutral-200/80 bg-white px-2 py-1.5 shadow-[0_1px_2px_rgb(15_23_42/0.04)] ${className}`.trim()}
      aria-label="执行步骤待办"
    >
      {steps.map((s, index) => {
        const st = statusByStepId[String(s.id)] ?? 'pending'
        const label =
          st === 'done' ? '已完成' : st === 'active' ? '进行中' : '待执行'
        return (
          <li
            key={`${s.id}-${index}`}
            className="flex items-start gap-2 text-neutral-800"
          >
            <span className="flex shrink-0 items-start pt-[0.06em]" title={label}>
              <TodoStatusIcon status={st} />
            </span>
            <span
              className={`min-w-0 flex-1 ${st === 'done' ? 'text-neutral-600' : ''}`}
              style={{ fontSize: 'var(--fa-chat-fs)', lineHeight: 'var(--fa-chat-lh)' }}
            >
              {s.title}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
