import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CheckSquare, Type, ThumbsUp, FileText, Shuffle } from 'lucide-react'
import { api } from '@/lib/api'
import type { Topic, StudyMode as StudyModeType, Session } from '@/types'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const MODES: { value: StudyModeType; icon: React.ReactNode }[] = [
  { value: 'multiple_choice', icon: <CheckSquare className="h-5 w-5" /> },
  { value: 'exact_answer', icon: <Type className="h-5 w-5" /> },
  { value: 'yes_no', icon: <ThumbsUp className="h-5 w-5" /> },
  { value: 'exam_question', icon: <FileText className="h-5 w-5" /> },
  { value: 'mixed', icon: <Shuffle className="h-5 w-5" /> },
]

const LIMITS: Array<number | null> = [5, 10, 20, 50, null]

export default function StudyMode() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [mode, setMode] = useState<StudyModeType>('multiple_choice')
  const [limit, setLimit] = useState<number | null>(20)

  const { data: topic } = useQuery({
    queryKey: ['topic', id],
    queryFn: () => api.get<Topic>(`/topics/${id}`),
    enabled: !!id,
  })

  const startMutation = useMutation({
    mutationFn: () =>
      api.post<Session>('/sessions', {
        topicId: id,
        mode,
        limit,
      }),
    onSuccess: (session) => navigate(`/sessions/${session.id}`),
  })

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6 max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">{t('study.title')}</h1>
        {topic && <p className="text-muted-foreground mt-1">{topic.title}</p>}
      </div>

      <div className="space-y-8">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            {t('study.modeLabel')}
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {MODES.map(({ value, icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={cn(
                  'flex items-start gap-3 p-4 rounded-lg border-2 text-left transition-colors',
                  mode === value
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-primary/40'
                )}
              >
                <span
                  className={cn(
                    'mt-0.5 shrink-0',
                    mode === value ? 'text-primary' : 'text-muted-foreground'
                  )}
                >
                  {icon}
                </span>
                <span>
                  <span className="block font-medium text-sm">
                    {t(`study.modes.${value}`)}
                  </span>
                  <span className="block text-xs text-muted-foreground mt-0.5">
                    {t(`study.modeDescriptions.${value}`)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            {t('study.limit')}
          </h2>
          <div className="flex flex-wrap gap-2">
            {LIMITS.map((l) => (
              <button
                key={l ?? 'all'}
                type="button"
                onClick={() => setLimit(l)}
                className={cn(
                  'px-4 py-2 rounded-full border text-sm font-medium transition-colors',
                  limit === l
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border hover:border-primary/50 text-foreground'
                )}
              >
                {l === null
                  ? t('study.limits.all')
                  : t('study.limits.n', { count: l })}
              </button>
            ))}
          </div>
        </div>

        <Button
          size="lg"
          className="w-full"
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
        >
          {startMutation.isPending ? t('common.loading') : t('study.start')}
        </Button>
      </div>
    </div>
  )
}
