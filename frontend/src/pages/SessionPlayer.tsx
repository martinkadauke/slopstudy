import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Zap, ChevronRight, CheckCircle2, XCircle, Sparkles } from 'lucide-react'
import { api } from '@/lib/api'
import type { Session, AnswerResult } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

export default function SessionPlayer() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [answerResult, setAnswerResult] = useState<AnswerResult | null>(null)
  const [input, setInput] = useState('')
  const [selectedOption, setSelectedOption] = useState<number | null>(null)
  const [yesNoAnswer, setYesNoAnswer] = useState<boolean | null>(null)

  const { data: session, isLoading } = useQuery({
    queryKey: ['session', id],
    queryFn: () => api.get<Session>(`/sessions/${id}`),
    enabled: !!id,
  })

  const answerMutation = useMutation({
    mutationFn: ({ cardId, answer }: { cardId: string; answer: string }) =>
      api.post<AnswerResult>(`/sessions/${id}/answers`, { cardId, answer }),
    onSuccess: (result) => setAnswerResult(result),
  })

  const skipMutation = useMutation({
    mutationFn: ({ cardId, force }: { cardId: string; force: boolean }) =>
      api.post<{ pointsDelta: number; currentPoints: number }>(
        `/sessions/${id}/skip`,
        { cardId, force }
      ),
    onSuccess: (result) => {
      setAnswerResult({
        correct: false,
        correctAnswer: '',
        pointsDelta: result.pointsDelta,
        currentPoints: result.currentPoints,
      })
    },
  })

  const handleNext = useCallback(() => {
    setAnswerResult(null)
    setInput('')
    setSelectedOption(null)
    setYesNoAnswer(null)
    queryClient.invalidateQueries({ queryKey: ['session', id] })
  }, [id, queryClient])

  // Detect session complete after advancing
  useEffect(() => {
    if (!isLoading && session && !answerResult) {
      if (session.status === 'completed' || session.currentCard === null) {
        navigate(`/sessions/${id}/summary`, { replace: true })
      }
    }
  }, [session, answerResult, isLoading, id, navigate])

  // Keyboard shortcuts for answering
  useEffect(() => {
    if (answerResult || !session?.currentCard) return
    const card = session.currentCard

    function handleKeyDown(e: KeyboardEvent) {
      if (card.type === 'multiple_choice') {
        const letterIdx = { a: 0, b: 1, c: 2, d: 3 }[e.key.toLowerCase()]
        if (letterIdx !== undefined && card.options && letterIdx < card.options.length) {
          e.preventDefault()
          answerMutation.mutate({ cardId: card.id, answer: card.options[letterIdx] })
          return
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
          e.preventDefault()
          setSelectedOption((prev) =>
            prev === null ? 0 : Math.min((card.options?.length ?? 4) - 1, prev + 1)
          )
        } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
          e.preventDefault()
          setSelectedOption((prev) =>
            prev === null ? 0 : Math.max(0, prev - 1)
          )
        } else if (e.key === 'Enter' && selectedOption !== null && card.options) {
          e.preventDefault()
          answerMutation.mutate({ cardId: card.id, answer: card.options[selectedOption] })
        }
      } else if (card.type === 'yes_no') {
        if (e.key === ' ') {
          e.preventDefault()
          setYesNoAnswer((prev) => (prev === null ? true : !prev))
        } else if (e.key === 'Enter' && yesNoAnswer !== null) {
          e.preventDefault()
          answerMutation.mutate({ cardId: card.id, answer: yesNoAnswer ? 'true' : 'false' })
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [session?.currentCard, answerResult, selectedOption, yesNoAnswer, answerMutation])

  // Keyboard: Enter to advance when in answered state
  useEffect(() => {
    if (!answerResult) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleNext()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [answerResult, handleNext])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <span className="text-muted-foreground">{t('common.loading')}</span>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center h-screen">
        <span className="text-muted-foreground">{t('common.error')}</span>
      </div>
    )
  }

  const card = session.currentCard
  const currentPoints = answerResult?.currentPoints ?? session.points
  const canAffordSkip = currentPoints >= session.skipCost
  const progressPct = session.totalCards > 0
    ? (session.currentIndex / session.totalCards) * 100
    : 0

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header: progress + points */}
      <div className="shrink-0 px-4 pt-4 pb-3 border-b">
        <div className="flex items-center justify-between mb-2 max-w-2xl mx-auto">
          <span className="text-sm text-muted-foreground">
            {t('session.progress', {
              current: Math.min(session.currentIndex + 1, session.totalCards),
              total: session.totalCards,
            })}
          </span>
          <span className="text-sm font-semibold text-primary">
            {t('session.points', { points: currentPoints })}
          </span>
        </div>
        <Progress value={progressPct} className="h-2 max-w-2xl mx-auto" />
      </div>

      {/* Card area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="max-w-2xl mx-auto">
          {/* Unanswered */}
          {card && !answerResult && (
            <div className="space-y-6">
              <p className="text-lg font-medium leading-relaxed">{card.question}</p>

              {card.type === 'multiple_choice' && card.options && (
                <div className="space-y-3">
                  {card.options.map((option, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => {
                        setSelectedOption(i)
                        answerMutation.mutate({ cardId: card.id, answer: option })
                      }}
                      disabled={answerMutation.isPending}
                      className={cn(
                        'w-full flex items-center gap-3 p-4 rounded-lg border-2 text-left transition-colors disabled:opacity-60',
                        selectedOption === i
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/50'
                      )}
                    >
                      <span
                        className={cn(
                          'shrink-0 w-8 h-8 rounded-full border-2 flex items-center justify-center text-sm font-bold',
                          selectedOption === i
                            ? 'border-primary text-primary'
                            : 'border-muted-foreground text-muted-foreground'
                        )}
                      >
                        {String.fromCharCode(65 + i)}
                      </span>
                      <span className="text-sm">{option}</span>
                    </button>
                  ))}
                </div>
              )}

              {card.type === 'yes_no' && (
                <div className="grid grid-cols-2 gap-4">
                  <Button
                    type="button"
                    variant={yesNoAnswer === true ? 'default' : 'outline'}
                    size="lg"
                    className="h-16 text-lg font-bold"
                    onClick={() => {
                      setYesNoAnswer(true)
                      answerMutation.mutate({ cardId: card.id, answer: 'true' })
                    }}
                    disabled={answerMutation.isPending}
                  >
                    {t('session.yes')}
                  </Button>
                  <Button
                    type="button"
                    variant={yesNoAnswer === false ? 'default' : 'outline'}
                    size="lg"
                    className="h-16 text-lg font-bold"
                    onClick={() => {
                      setYesNoAnswer(false)
                      answerMutation.mutate({ cardId: card.id, answer: 'false' })
                    }}
                    disabled={answerMutation.isPending}
                  >
                    {t('session.no')}
                  </Button>
                </div>
              )}

              {card.type === 'exact_answer' && (
                <div className="space-y-3">
                  <Input
                    placeholder={t('session.yourAnswer')}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && input.trim()) {
                        e.preventDefault()
                        answerMutation.mutate({ cardId: card.id, answer: input.trim() })
                      }
                    }}
                    disabled={answerMutation.isPending}
                    autoFocus
                  />
                  <Button
                    onClick={() => {
                      if (input.trim()) {
                        answerMutation.mutate({ cardId: card.id, answer: input.trim() })
                      }
                    }}
                    disabled={!input.trim() || answerMutation.isPending}
                  >
                    {answerMutation.isPending ? t('common.loading') : t('session.submit')}
                  </Button>
                </div>
              )}

              {card.type === 'exam_question' && (
                <div className="space-y-3">
                  <Textarea
                    placeholder={t('session.detailedAnswer')}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    rows={6}
                    disabled={answerMutation.isPending}
                    autoFocus
                  />
                  <Button
                    onClick={() => {
                      if (input.trim()) {
                        answerMutation.mutate({ cardId: card.id, answer: input.trim() })
                      }
                    }}
                    disabled={!input.trim() || answerMutation.isPending}
                  >
                    {answerMutation.isPending ? t('common.loading') : t('session.submit')}
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* Answered / revealed */}
          {answerResult && (
            <div className="space-y-4">
              {card && (
                <p className="text-lg font-medium leading-relaxed">{card.question}</p>
              )}

              <div
                className={cn(
                  'flex items-center gap-3 p-4 rounded-lg',
                  answerResult.correct
                    ? 'bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200'
                    : 'bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200'
                )}
              >
                {answerResult.correct ? (
                  <CheckCircle2 className="h-5 w-5 shrink-0" />
                ) : (
                  <XCircle className="h-5 w-5 shrink-0" />
                )}
                <span className="font-semibold flex-1">
                  {answerResult.correct ? t('session.correct') : t('session.incorrect')}
                </span>
                {answerResult.pointsDelta > 0 && (
                  <span className="font-bold text-sm">
                    {t('session.pointsDelta', { points: answerResult.pointsDelta })}
                  </span>
                )}
              </div>

              {!answerResult.correct && answerResult.correctAnswer && (
                <div className="p-3 rounded-lg bg-muted text-sm">
                  <span className="font-medium">{t('session.correctAnswer')}</span>{' '}
                  {answerResult.correctAnswer}
                </div>
              )}

              {answerResult.explanation && (
                <div className="p-3 rounded-lg bg-muted/50 border border-border text-sm">
                  <span className="font-medium">{t('session.explanation')}</span>{' '}
                  {answerResult.explanation}
                </div>
              )}

              {answerResult.llmFeedback && (
                <div className="p-4 rounded-lg border border-primary/20 bg-primary/5 text-sm">
                  <div className="flex items-center gap-2 font-medium mb-2">
                    <Sparkles className="h-4 w-4 text-primary" />
                    {t('session.aiFeedback')}
                  </div>
                  <p className="text-muted-foreground leading-relaxed">
                    {answerResult.llmFeedback}
                  </p>
                </div>
              )}

              <Button className="w-full" onClick={handleNext}>
                {t('session.next')}
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Skip bar */}
      {card && !answerResult && (
        <div className="shrink-0 border-t px-4 py-3 flex items-center gap-2 bg-background">
          <div className="flex flex-wrap gap-2 flex-1">
            {canAffordSkip && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground h-8"
                onClick={() => skipMutation.mutate({ cardId: card.id, force: false })}
                disabled={skipMutation.isPending}
              >
                {t('session.skip', { cost: session.skipCost })}
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground h-8"
              onClick={() => skipMutation.mutate({ cardId: card.id, force: true })}
              disabled={skipMutation.isPending}
            >
              {t('session.skipAnyway', { penalty: session.skipPenalty })}
            </Button>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
            <Zap className="h-3 w-3" />
            <span>{currentPoints}</span>
          </div>
        </div>
      )}
    </div>
  )
}
