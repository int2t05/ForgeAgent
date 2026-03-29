/**
 * 侧边导航组件：首页、任务、设置、关于。
 */

import { NavLink } from 'react-router'

interface NavItem {
  to: string
  label: string
  icon: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '首页', icon: '⌂' },
  { to: '/tasks', label: '任务', icon: '☰' },
  { to: '/settings', label: '设置', icon: '⚙' },
  { to: '/about', label: '关于', icon: 'ⓘ' },
]

export function Sidebar() {
  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r border-neutral-200 bg-white">
      {/* 品牌标识 */}
      <div className="flex h-14 items-center gap-2 border-b border-neutral-200 px-5">
        <span className="text-lg font-semibold text-blue-600">Forge</span>
        <span className="text-lg font-semibold text-neutral-800">Agent</span>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                isActive
                  ? 'bg-blue-50 font-medium text-blue-700'
                  : 'text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900'
              }`
            }
          >
            <span className="text-base">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* 底栏 */}
      <div className="border-t border-neutral-200 px-5 py-3">
        <p className="text-xs text-neutral-400">ForgeAgent MVP</p>
      </div>
    </aside>
  )
}
