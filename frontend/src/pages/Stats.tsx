import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '@/lib/api'
import type { UserStats } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'

export default function Stats() {
  const { t } = useTranslation()

  const { data: stats, isLoading } = useQuery({
    queryKey: ['userStats'],
    queryFn: () => api.get<UserStats>('/users/me/stats'),
  })

  if (isLoading) {
    return (
      <div className="p-6 text-center text-muted-foreground">{t('common.loading')}</div>
    )
  }

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('stats.title')}</h1>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('stats.points')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{stats?.points ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('stats.streak')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">
              {stats?.streak ?? 0}
            </div>
            <div className="text-xs text-muted-foreground">{t('common.days')}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('stats.sessions')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{stats?.sessions ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('stats.accuracy')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{stats?.accuracy ?? 0}%</div>
            <Progress value={stats?.accuracy ?? 0} className="mt-2 h-2" />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
