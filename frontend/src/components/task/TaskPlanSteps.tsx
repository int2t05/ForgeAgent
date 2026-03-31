import type { PlanStep } from '@/utils/normalizeTaskPlan'

interface TaskPlanStepsProps {
  steps: PlanStep[]
  className?: string
}

export function TaskPlanSteps({ steps, className = '' }: TaskPlanStepsProps) {
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
          <span className="min-w-0 flex-1" style={{ fontSize: 'var(--fa-chat-fs)', lineHeight: 'var(--fa-chat-lh)' }}>
            {s.title}
          </span>
        </li>
      ))}
    </ol>
  )
}
