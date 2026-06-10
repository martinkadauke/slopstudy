import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { Badge } from './ui/badge'

const routeTitles: Record<string, string> = {
  '/': 'nav.topics',
  '/stats': 'nav.stats',
  '/profile': 'nav.profile',
  '/settings': 'nav.settings',
}

export function MobileHeader() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const user = useAuthStore((s) => s.user)

  const titleKey = routeTitles[pathname] ?? 'nav.topics'

  return (
    <header className="lg:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-card">
      <div className="flex items-center gap-2">
        <BookOpen className="h-5 w-5 text-primary" />
        <span className="font-semibold text-base">{t(titleKey)}</span>
      </div>
      <Badge variant="secondary" className="text-xs">
        {user?.points ?? 0} {t('common.pts')}
      </Badge>
    </header>
  )
}
