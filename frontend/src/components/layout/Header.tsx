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
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-6">
      <h1 className="text-base font-semibold text-neutral-900">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}
