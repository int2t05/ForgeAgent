import type { PlanStep } from '@/lib/normalizeTaskPlan'

interface TaskPlanStepsProps {
  steps: PlanStep[]
  className?: string
}

export function TaskPlanSteps({ steps, className = '' }: TaskPlanStepsProps) {
  return (
    <ol
      className={`fa-task-plan-steps list-none rounded-lg border border-neutral-200/80 bg-white/90 px-2 py-1.5 shadow-[0_1px_2px_rgb(15_23_42/0.04)] ${className}`.trim()}
    >
      {steps.map((s, index) => (
        <li
          key={`${s.id}-${index}`}
          className="flex items-start gap-2 text-neutral-800"
        >
          <span
            className="mt-[0.15em] inline-flex h-[1.15em] min-w-[1.15em] shrink-0 items-center justify-center rounded-full border border-primary-200/80 bg-primary-50/90 px-0.5 font-mono font-semibold text-primary-700 tabular-nums leading-none"
            style={{ fontSize: 'calc(var(--fa-chat-fs) * 0.72)' }}
            aria-hidden
          >
            {s.id}
          </span>
          <span className="min-w-0 flex-1" style={{ fontSize: 'var(--fa-chat-fs)', lineHeight: 'var(--fa-chat-lh)' }}>
            {s.title}
          </span>
        </li>
      ))}
    </ol>
  )
}
