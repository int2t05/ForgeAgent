/**
 * 执行模式选择区域：auto / confirm / learn 三种模式切换。
 */

import type { ExecutionMode } from '@/types/settings'

const MODES: { value: ExecutionMode; label: string; desc: string }[] = [
  {
    value: 'auto',
    label: '自动执行',
    desc: '所有工具（含敏感操作）直接执行，无需人工确认',
  },
  {
    value: 'confirm',
    label: '每次确认',
    desc: '每次敏感工具（Python REPL、Shell、写文件等）执行前需人工批准或拒绝',
  },
  {
    value: 'learn',
    label: '学习模式',
    desc: '首次使用某敏感工具时需确认，之后同名工具自动放行（可重置已批准列表）',
  },
]

export function ExecutionModeSection({
  value,
  onChange,
}: {
  value: ExecutionMode
  onChange: (mode: ExecutionMode) => void
}) {
  return (
    <section>
      <h2 className="mb-3 text-base font-semibold text-neutral-800">
        工具执行策略
      </h2>
      <div className="flex flex-col gap-3">
        {MODES.map((mode) => (
          <label
            key={mode.value}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
              value === mode.value
                ? 'border-blue-400 bg-blue-50/60'
                : 'border-neutral-200 bg-white hover:border-neutral-300'
            }`}
          >
            <input
              type="radio"
              name="execution_mode"
              value={mode.value}
              checked={value === mode.value}
              onChange={() => onChange(mode.value)}
              className="mt-0.5 h-4 w-4 shrink-0 text-blue-600"
            />
            <div className="min-w-0">
              <span className="text-sm font-medium text-neutral-800">
                {mode.label}
              </span>
              <p className="mt-0.5 text-xs leading-relaxed text-neutral-500">
                {mode.desc}
              </p>
            </div>
          </label>
        ))}
      </div>
      <p className="fa-text-caption mt-1.5 text-neutral-500">
        敏感工具包括：python_repl、shell、write_file 及 MCP 写操作。
        切换模式后需点「保存」生效。
      </p>
    </section>
  )
}
