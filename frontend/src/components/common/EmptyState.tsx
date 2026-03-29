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
    <div className="fa-card flex flex-col items-center justify-center gap-2 border-dashed py-14 text-center shadow-none">
      <div
        className="h-10 w-10 rounded-lg border-2 border-neutral-200 border-dashed"
        aria-hidden
      />
      <h3 className="font-medium text-base text-neutral-700">{title}</h3>
      {description && (
        <p className="max-w-sm text-sm text-neutral-500">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
