/**
 * 空状态占位组件：列表无数据时展示。
 */

interface EmptyStateProps {
  /** 主标题。 */
  title?: string
  /** 描述文案。 */
  description?: string
  /** 自定义操作区域（如按钮）。 */
  action?: React.ReactNode
}

export function EmptyState({
  title = '暂无数据',
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="fa-card flex flex-col items-center justify-center gap-3 border-dashed border-neutral-300/60 bg-neutral-50/90 py-14 text-center shadow-none">
      <div
        className="flex h-12 w-12 items-center justify-center rounded-xl border border-neutral-200/90 bg-gradient-to-br from-neutral-50 to-white text-primary-500 shadow-inner"
        aria-hidden
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" className="opacity-85">
          <path
            d="M4 14.5L9 9.5l4 4 7-7M4 20h16"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <h3 className="font-display font-medium text-base text-neutral-800">{title}</h3>
      {description && (
        <p className="fa-text-caption max-w-sm text-neutral-500">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
