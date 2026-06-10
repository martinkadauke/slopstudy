import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Flame, Plus, Minus } from 'lucide-react'
import { api } from '@/lib/api'
import type { SessionSummaryData } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function SessionSummary() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation()
  const navigate = useNavigate()

  const { data: summary, isLoading } = useQuery({
    queryKey: ['sessionSummary', id],
    queryFn: () => api.get<SessionSummaryData>(`/sessions/${id}/summary`),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <span className="text-muted-foreground">{t('common.loading')}</span>
      </div>
    )
  }

  if (!summary) {
    return (
      <div className="flex items-center justify-center h-screen">
        <span className="text-muted-foreground">{t('common.error')}</span>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-4 md:p-6">
      <div className="max-w-lg mx-auto space-y-6">
        {/* Trophy */}
        <div className="text-center py-6">
          <div
            className="text-7xl mb-4 inline-block"
            style={{
              animation: 'trophy-bounce 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) both',
            }}
          >
            🏆
          </div>
          <h1 className="text-2xl font-bold">{t('summary.title')}</h1>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: t('summary.answered'), value: summary.answered },
            { label: t('summary.correct'), value: summary.correct },
            { label: t('summary.skipped'), value: summary.skipped },
            {
              label: t('summary.accuracy'),
              value: `${summary.accuracy}%`,
            },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-xl border bg-card p-4 text-center">
              <div className="text-2xl font-bold text-primary">{value}</div>
              <div className="text-xs text-muted-foreground mt-1">{label}</div>
            </div>
          ))}
        </div>

        {/* Points breakdown */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('summary.breakdown')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <PointRow
              icon={<Plus className="h-3.5 w-3.5" />}
              label={t('summary.fromAnswers')}
              value={summary.pointsFromAnswers}
              positive
            />
            <PointRow
              icon={<Plus className="h-3.5 w-3.5" />}
              label={t('summary.participation')}
              value={summary.participationBonus}
              positive
            />
            {summary.streakBonus > 0 && (
              <PointRow
                icon={<Flame className="h-3.5 w-3.5 text-orange-500" />}
                label={
                  <span className="flex items-center gap-1.5">
                    {t('summary.streakBonus')}
                    <span className="flex items-center gap-0.5 text-orange-500 font-medium">
                      <Flame className="h-3 w-3" />
                      {summary.streakDays}
                    </span>
                  </span>
                }
                value={summary.streakBonus}
                positive
              />
            )}
            {summary.spentOnSkips > 0 && (
              <PointRow
                icon={<Minus className="h-3.5 w-3.5" />}
                label={t('summary.spentOnSkips')}
                value={summary.spentOnSkips}
                positive={false}
              />
            )}
            <div className="border-t pt-2 mt-2 flex items-center justify-between">
              <span className="font-semibold text-sm">{t('summary.total')}</span>
              <span className="font-bold text-primary text-lg">
                +{summary.total}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* New badges */}
        {summary.newBadges.length > 0 && (
          <Card className="border-primary/30 bg-primary/5">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{t('summary.newBadges')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-3">
                {summary.newBadges.map((badge) => (
                  <div
                    key={badge.id}
                    className="flex flex-col items-center text-center p-3 rounded-lg border border-primary/30 bg-background gap-1.5"
                    style={{ animation: 'badge-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) both' }}
                  >
                    <span className="text-3xl">{badge.icon}</span>
                    <span className="text-xs font-medium">{badge.name}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* CTAs */}
        <div className="grid grid-cols-2 gap-3">
          <Button
            variant="outline"
            onClick={() => navigate(`/topics/${summary.topicId}/study`)}
          >
            {t('summary.studyAgain')}
          </Button>
          <Button onClick={() => navigate('/')}>
            {t('summary.backToTopics')}
          </Button>
        </div>
      </div>

      <style>{`
        @keyframes trophy-bounce {
          from { transform: scale(0) rotate(-15deg); opacity: 0; }
          to { transform: scale(1) rotate(0deg); opacity: 1; }
        }
        @keyframes badge-pop {
          from { transform: scale(0.5); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

function PointRow({
  icon,
  label,
  value,
  positive,
}: {
  icon: React.ReactNode
  label: React.ReactNode
  value: number
  positive: boolean
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className={positive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
          {icon}
        </span>
        {label}
      </div>
      <span
        className={
          positive
            ? 'font-medium text-green-600 dark:text-green-400'
            : 'font-medium text-red-600 dark:text-red-400'
        }
      >
        {positive ? '+' : '−'}
        {value}
      </span>
    </div>
  )
}
