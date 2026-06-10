import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Flame, Trophy, Target, Zap, BookOpen } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { api } from '@/lib/api'
import type { UserStats, UserBadge, LeaderboardEntry, PointHistoryEntry } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'

export default function Stats() {
  const { t } = useTranslation()

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['userStats'],
    queryFn: () => api.get<UserStats>('/users/me/stats'),
  })

  const { data: badges } = useQuery({
    queryKey: ['userBadges'],
    queryFn: () => api.get<UserBadge[]>('/users/me/badges'),
  })

  const { data: leaderboard } = useQuery({
    queryKey: ['leaderboard'],
    queryFn: () => api.get<LeaderboardEntry[]>('/leaderboard'),
  })

  const { data: pointHistory } = useQuery({
    queryKey: ['pointHistory'],
    queryFn: () => api.get<PointHistoryEntry[]>('/users/me/point-history'),
  })

  if (statsLoading) {
    return (
      <div className="p-6 text-center text-muted-foreground">{t('common.loading')}</div>
    )
  }

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6 max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">{t('stats.title')}</h1>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5" />
              {t('stats.points')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{stats?.points ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Flame className="h-3.5 w-3.5 text-orange-500" />
              {t('stats.streak')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <div className="text-3xl font-bold text-primary">{stats?.streak ?? 0}</div>
              <div className="text-sm text-muted-foreground">{t('stats.days')}</div>
            </div>
            {(stats?.streak ?? 0) > 0 && (
              <div className="flex gap-0.5 mt-2">
                {Array.from({ length: Math.min(stats!.streak, 7) }).map((_, i) => (
                  <Flame
                    key={i}
                    className="h-4 w-4 text-orange-500"
                    style={{ opacity: 0.4 + (i / Math.min(stats!.streak, 7)) * 0.6 }}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <BookOpen className="h-3.5 w-3.5" />
              {t('stats.sessions')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{stats?.sessions ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Target className="h-3.5 w-3.5" />
              {t('stats.accuracy')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{stats?.accuracy ?? 0}%</div>
            <Progress value={stats?.accuracy ?? 0} className="mt-2 h-1.5" />
          </CardContent>
        </Card>
      </div>

      {/* Point history chart */}
      {pointHistory && pointHistory.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center justify-between">
              {t('stats.pointHistory')}
              <span className="text-xs font-normal text-muted-foreground">
                {t('stats.last30Days')}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={pointHistory} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => {
                    const d = new Date(v)
                    return `${d.getMonth() + 1}/${d.getDate()}`
                  }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  cursor={{ fill: 'hsl(var(--accent))' }}
                  contentStyle={{
                    background: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: '12px',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                  labelFormatter={(v) => new Date(v).toLocaleDateString()}
                />
                <Bar
                  dataKey="points"
                  fill="hsl(var(--primary))"
                  radius={[3, 3, 0, 0]}
                  maxBarSize={32}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Leaderboard */}
      {leaderboard && leaderboard.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Trophy className="h-4 w-4 text-yellow-500" />
              {t('stats.leaderboard')}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {leaderboard.map((entry) => (
                <div
                  key={entry.rank}
                  className="flex items-center gap-3 px-6 py-3"
                >
                  <span
                    className={`w-6 text-center text-sm font-bold shrink-0 ${
                      entry.rank === 1
                        ? 'text-yellow-500'
                        : entry.rank === 2
                        ? 'text-slate-400'
                        : entry.rank === 3
                        ? 'text-amber-600'
                        : 'text-muted-foreground'
                    }`}
                  >
                    {entry.rank === 1
                      ? '🥇'
                      : entry.rank === 2
                      ? '🥈'
                      : entry.rank === 3
                      ? '🥉'
                      : entry.rank}
                  </span>
                  <span className="flex-1 text-sm font-medium">{entry.username}</span>
                  <span className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Zap className="h-3.5 w-3.5 text-primary" />
                    {entry.points}
                  </span>
                  {entry.streak > 0 && (
                    <span className="flex items-center gap-1 text-xs text-orange-500 w-12 justify-end">
                      <Flame className="h-3.5 w-3.5" />
                      {entry.streak}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Badges */}
      {badges && badges.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('stats.badges')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-3 sm:grid-cols-6">
              {badges.map((badge) => (
                <div
                  key={badge.id}
                  className={`flex flex-col items-center text-center p-3 rounded-lg border gap-1.5 transition-colors ${
                    badge.earned
                      ? 'border-primary/30 bg-primary/5'
                      : 'border-border bg-muted/40 opacity-50'
                  }`}
                  title={
                    badge.earned ? badge.description : t('profile.badges.unearned')
                  }
                >
                  <span className="text-2xl">{badge.icon}</span>
                  <span className="text-xs font-medium leading-tight line-clamp-2">
                    {badge.name}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
