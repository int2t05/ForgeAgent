import type { PlanStep } from '@/lib/normalizeTaskPlan'

interface TaskPlanStepsProps {
  steps: PlanStep[]
  className?: string
}

export function TaskPlanSteps({ steps, className = '' }: TaskPlanStepsProps) {
  return (
    <ol
      className={`list-none space-y-1.5 rounded-lg border border-neutral-200/90 bg-white/80 px-3 py-2.5 text-sm shadow-[0_1px_2px_rgb(15_23_42/0.04)] ${className}`.trim()}
    >
      {steps.map((s, index) => (
        <li
          key={`${s.id}-${index}`}
          className="flex items-start gap-2.5 leading-relaxed text-neutral-800"
        >
          <span
            className="mt-[0.2rem] inline-flex h-3.5 min-w-3.5 shrink-0 items-center justify-center rounded-full border border-primary-200/80 bg-primary-50/90 px-[3px] font-mono text-[0.625rem] font-semibold text-primary-700 tabular-nums leading-none"
            aria-hidden
          >
            {s.id}
          </span>
          <span className="min-w-0 flex-1">{s.title}</span>
        </li>
      ))}
    </ol>
  )
}
