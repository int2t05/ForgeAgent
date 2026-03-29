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
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      <div className="text-4xl text-neutral-300">○</div>
      <h3 className="text-base font-medium text-neutral-700">{title}</h3>
      {description && (
        <p className="max-w-sm text-sm text-neutral-500">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
