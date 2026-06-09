import { useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Upload, Link as LinkIcon, AlignLeft, File, Globe, Trash2, AlertCircle, PlayCircle } from 'lucide-react'
import { api } from '@/lib/api'
import type { Topic, Source } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

function statusVariant(status: Topic['status']) {
  const map = { draft: 'draft', generating: 'generating', ready: 'ready', failed: 'failed' } as const
  return map[status]
}

function sourceIcon(type: Source['type']) {
  if (type === 'file') return <File className="h-4 w-4 text-muted-foreground" />
  if (type === 'url') return <Globe className="h-4 w-4 text-muted-foreground" />
  return <AlignLeft className="h-4 w-4 text-muted-foreground" />
}

export default function TopicDetail() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [urlDialogOpen, setUrlDialogOpen] = useState(false)
  const [textDialogOpen, setTextDialogOpen] = useState(false)
  const [urlValue, setUrlValue] = useState('')
  const [textValue, setTextValue] = useState('')

  const { data: topic, isLoading: topicLoading } = useQuery({
    queryKey: ['topic', id],
    queryFn: () => api.get<Topic>(`/topics/${id}`),
    refetchInterval: (query) => {
      const data = query.state.data as Topic | undefined
      return data?.status === 'generating' ? 5000 : false
    },
    enabled: !!id,
  })

  const { data: sources, isLoading: sourcesLoading } = useQuery({
    queryKey: ['sources', id],
    queryFn: () => api.get<Source[]>(`/topics/${id}/sources`),
    enabled: !!id,
  })

  const uploadFileMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<Source>(`/topics/${id}/sources`, form)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sources', id] }),
  })

  const addUrlMutation = useMutation({
    mutationFn: (url: string) => api.post<Source>(`/topics/${id}/sources/url`, { url }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources', id] })
      setUrlDialogOpen(false)
      setUrlValue('')
    },
  })

  const addTextMutation = useMutation({
    mutationFn: (content: string) => api.post<Source>(`/topics/${id}/sources/text`, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources', id] })
      setTextDialogOpen(false)
      setTextValue('')
    },
  })

  const deleteSourceMutation = useMutation({
    mutationFn: (sourceId: string) =>
      api.delete(`/topics/${id}/sources/${sourceId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sources', id] }),
  })

  const generateMutation = useMutation({
    mutationFn: () => api.post(`/topics/${id}/generate`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['topic', id] }),
  })

  if (topicLoading) {
    return (
      <div className="p-6 text-center text-muted-foreground">{t('common.loading')}</div>
    )
  }

  if (!topic) {
    return (
      <div className="p-6 text-center text-muted-foreground">{t('common.error')}</div>
    )
  }

  const hasSources = !!sources?.length
  const canGenerate = hasSources && topic.status !== 'generating'

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <div className="flex items-start gap-3 mb-2">
          <h1 className="text-2xl font-bold flex-1">{topic.title}</h1>
          <Badge variant={statusVariant(topic.status)}>
            {t(`topicDetail.status.${topic.status}`)}
          </Badge>
        </div>
        {topic.description && (
          <p className="text-muted-foreground">{topic.description}</p>
        )}
      </div>

      {topic.status === 'failed' && (
        <div className="flex items-center gap-2 p-3 mb-4 rounded-md bg-destructive/10 text-destructive text-sm">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {t('topicDetail.error')}
        </div>
      )}

      {topic.status === 'ready' && (
        <Card className="mb-6 border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950">
          <CardContent className="flex items-center justify-between pt-6">
            <span className="font-medium text-green-800 dark:text-green-200">
              {t('topicDetail.cardCount', { count: topic.cardCount })}
            </span>
            <Button onClick={() => navigate(`/topics/${id}/study`)}>
              <PlayCircle className="h-4 w-4" />
              {t('topicDetail.startStudying')}
            </Button>
          </CardContent>
        </Card>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">{t('topicDetail.sources')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {sourcesLoading ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : !sources?.length ? (
            <p className="text-sm text-muted-foreground">{t('topicDetail.noSources')}</p>
          ) : (
            <ul className="space-y-2">
              {sources.map((source) => (
                <li
                  key={source.id}
                  className="flex items-center gap-3 p-2 rounded-md border border-border"
                >
                  {sourceIcon(source.type)}
                  <span className="flex-1 text-sm truncate">{source.name}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    onClick={() => deleteSourceMutation.mutate(source.id)}
                    disabled={deleteSourceMutation.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span className="sr-only">{t('topicDetail.delete')}</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap gap-2 pt-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) uploadFileMutation.mutate(file)
                e.target.value = ''
              }}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadFileMutation.isPending}
            >
              <Upload className="h-3.5 w-3.5" />
              {t('topicDetail.uploadFile')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setUrlDialogOpen(true)}
            >
              <LinkIcon className="h-3.5 w-3.5" />
              {t('topicDetail.addUrl')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setTextDialogOpen(true)}
            >
              <AlignLeft className="h-3.5 w-3.5" />
              {t('topicDetail.addText')}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={canGenerate ? -1 : 0} className="inline-block">
              <Button
                onClick={() => generateMutation.mutate()}
                disabled={!canGenerate || generateMutation.isPending}
              >
                {generateMutation.isPending || topic.status === 'generating'
                  ? t('common.loading')
                  : t('topicDetail.generatePlan')}
              </Button>
            </span>
          </TooltipTrigger>
          {!hasSources && (
            <TooltipContent>
              <p>{t('topicDetail.noSourcesHint')}</p>
            </TooltipContent>
          )}
        </Tooltip>
      </div>

      <Dialog open={urlDialogOpen} onOpenChange={setUrlDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('topicDetail.addUrlDialog.title')}</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (urlValue.trim()) addUrlMutation.mutate(urlValue.trim())
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="url-input">{t('topicDetail.addUrlDialog.label')}</Label>
              <Input
                id="url-input"
                type="url"
                placeholder={t('topicDetail.addUrlDialog.placeholder')}
                value={urlValue}
                onChange={(e) => setUrlValue(e.target.value)}
                required
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setUrlDialogOpen(false)}>
                {t('topicDetail.addUrlDialog.cancel')}
              </Button>
              <Button type="submit" disabled={addUrlMutation.isPending}>
                {addUrlMutation.isPending ? t('common.loading') : t('topicDetail.addUrlDialog.submit')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={textDialogOpen} onOpenChange={setTextDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('topicDetail.addTextDialog.title')}</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (textValue.trim()) addTextMutation.mutate(textValue.trim())
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="text-input">{t('topicDetail.addTextDialog.label')}</Label>
              <Textarea
                id="text-input"
                placeholder={t('topicDetail.addTextDialog.placeholder')}
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                rows={6}
                required
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setTextDialogOpen(false)}>
                {t('topicDetail.addTextDialog.cancel')}
              </Button>
              <Button type="submit" disabled={addTextMutation.isPending}>
                {addTextMutation.isPending ? t('common.loading') : t('topicDetail.addTextDialog.submit')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
