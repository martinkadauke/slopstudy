import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus, CalendarDays, Layers } from 'lucide-react'
import { api } from '@/lib/api'
import type { Topic } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

function statusVariant(status: Topic['status']) {
  const map = {
    draft: 'draft',
    generating: 'generating',
    ready: 'ready',
    failed: 'failed',
  } as const
  return map[status]
}

function TopicCard({ topic }: { topic: Topic }) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => navigate(`/topics/${topic.id}`)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base leading-tight">{topic.title}</CardTitle>
          <Badge variant={statusVariant(topic.status)} className="shrink-0">
            {t(`topics.card.status.${topic.status}`)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pb-2">
        {topic.description && (
          <p className="text-sm text-muted-foreground line-clamp-2">{topic.description}</p>
        )}
      </CardContent>
      <CardFooter className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <Layers className="h-3 w-3" />
          {t('topics.card.cards', { count: topic.cardCount })}
        </span>
        <span className="flex items-center gap-1">
          <CalendarDays className="h-3 w-3" />
          {new Date(topic.createdAt).toLocaleDateString()}
        </span>
      </CardFooter>
    </Card>
  )
}

export default function Topics() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')

  const { data: topics, isLoading } = useQuery({
    queryKey: ['topics'],
    queryFn: () => api.get<Topic[]>('/topics'),
    refetchInterval: (query) => {
      const data = query.state.data as Topic[] | undefined
      return data?.some((t) => t.status === 'generating') ? 5000 : false
    },
  })

  const createMutation = useMutation({
    mutationFn: (data: { title: string; description?: string }) =>
      api.post<Topic>('/topics', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
      setOpen(false)
      setTitle('')
      setDescription('')
    },
  })

  function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    createMutation.mutate({ title: title.trim(), description: description.trim() || undefined })
  }

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t('topics.title')}</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="h-4 w-4" />
              {t('topics.newTopic')}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('topics.create.title')}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="topic-title">{t('topics.create.titleLabel')}</Label>
                <Input
                  id="topic-title"
                  placeholder={t('topics.create.titlePlaceholder')}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="topic-description">{t('topics.create.description')}</Label>
                <Textarea
                  id="topic-description"
                  placeholder={t('topics.create.descriptionPlaceholder')}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                />
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setOpen(false)}
                >
                  {t('topics.create.cancel')}
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? t('common.loading') : t('topics.create.submit')}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">{t('common.loading')}</div>
      ) : !topics?.length ? (
        <div className="text-center py-12 text-muted-foreground">{t('topics.empty')}</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {topics.map((topic) => (
            <TopicCard key={topic.id} topic={topic} />
          ))}
        </div>
      )}
    </div>
  )
}
