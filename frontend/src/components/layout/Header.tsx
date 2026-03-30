/**
 * 顶栏组件：页面标题与可选面包屑。
 */

interface HeaderProps {
  /** 当前页面标题。 */
  title: string
  /** 可选右侧操作区域。 */
  actions?: React.ReactNode
}

export function Header({ title, actions }: HeaderProps) {
  return (
    <header className="fa-page-header">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="h-6 w-1 shrink-0 rounded-full bg-primary-600" aria-hidden />
        <h1 className="font-display min-w-0 truncate text-base font-semibold tracking-tight text-neutral-900">
          {title}
        </h1>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
