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
      <h1 className="text-base font-semibold tracking-tight text-neutral-900">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}
