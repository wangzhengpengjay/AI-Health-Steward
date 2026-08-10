import { NavLink } from 'react-router-dom'
import MemberSwitcher from './MemberSwitcher'

interface NavItem {
  to: string
  label: string
  icon: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/home', label: '家庭速览', icon: 'home' },
  { to: '/dashboard', label: '画像看板', icon: 'dashboard' },
  { to: '/chat', label: 'AI 咨询', icon: 'forum' },
  { to: '/reports', label: '报告管理', icon: 'description' },
  { to: '/checkup', label: '体检推荐', icon: 'monitor_heart' },
  { to: '/summaries', label: '健康小结', icon: 'summarize' },
  { to: '/members', label: '成员管理', icon: 'group' },
  { to: '/metric-input', label: '健康指标', icon: 'monitoring' },
  { to: '/settings', label: '设置', icon: 'settings' },
]

export default function Sidebar() {
  return (
    <aside className="flex w-64 flex-col border-r border-slate-200 bg-bg-primary">
      {/* Logo / title */}
      <div className="flex h-16 items-center gap-2 border-b border-slate-200 px-6">
        <span className="material-symbols-rounded text-2xl text-primary">
          health_and_safety
        </span>
        <span className="text-lg font-semibold text-slate-800">
          家庭健康管家
        </span>
      </div>

      {/* Member switcher */}
      <div className="border-b border-slate-200 p-4">
        <MemberSwitcher />
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-field px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary-light text-primary-active'
                  : 'text-slate-600 hover:bg-bg-tertiary'
              }`
            }
          >
            <span className="material-symbols-rounded text-xl">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
