import { NavLink } from 'react-router-dom'
import { BookOpen, BarChart2, User, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

const tabs = [
  { to: '/', icon: BookOpen, labelKey: 'nav.topics', exact: true },
  { to: '/stats', icon: BarChart2, labelKey: 'nav.stats' },
  { to: '/profile', icon: User, labelKey: 'nav.profile' },
  { to: '/settings', icon: Settings, labelKey: 'nav.settings' },
]

export function BottomTabBar() {
  const { t } = useTranslation()

  return (
    <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-border bg-card">
      <div className="flex">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.exact}
            className={({ isActive }) =>
              cn(
                'flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground'
              )
            }
          >
            <tab.icon className="h-5 w-5" />
            <span>{t(tab.labelKey)}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
