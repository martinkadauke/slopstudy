import { NavLink, useNavigate } from 'react-router-dom'
import { BookOpen, BarChart2, User, Settings, LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/authStore'
import { Badge } from './ui/badge'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', icon: BookOpen, labelKey: 'nav.topics', exact: true },
  { to: '/stats', icon: BarChart2, labelKey: 'nav.stats' },
  { to: '/profile', icon: User, labelKey: 'nav.profile' },
  { to: '/settings', icon: Settings, labelKey: 'nav.settings' },
]

export function Sidebar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const initials = user?.username?.[0]?.toUpperCase() ?? '?'

  return (
    <aside className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-64 border-r border-border bg-card z-30">
      <div className="flex items-center gap-2 px-6 py-5 border-b border-border">
        <BookOpen className="h-6 w-6 text-primary" />
        <span className="font-bold text-lg tracking-tight">SlopStudy</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.exact}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )
            }
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {t(item.labelKey)}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-border space-y-3">
        <div className="flex items-center gap-3 px-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{user?.username}</p>
            <div className="mt-0.5">
              <Badge variant="secondary" className="text-xs">
                {user?.points ?? 0} {t('common.pts')}
              </Badge>
            </div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {t('nav.logout')}
        </button>
      </div>
    </aside>
  )
}
