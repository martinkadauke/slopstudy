import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ChevronDown } from 'lucide-react'
import { api } from '@/lib/api'
import type { OllamaSettings, SmtpSettings } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export default function Settings() {
  const { t } = useTranslation()

  const [ollamaUrl, setOllamaUrl] = useState('')
  const [ollamaModel, setOllamaModel] = useState('')
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)

  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('587')
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpFrom, setSmtpFrom] = useState('')
  const [smtpTls, setSmtpTls] = useState(true)

  useQuery({
    queryKey: ['settings', 'ollama'],
    queryFn: async () => {
      const data = await api.get<OllamaSettings>('/settings/ollama')
      setOllamaUrl(data.url ?? '')
      setOllamaModel(data.model ?? '')
      return data
    },
  })

  useQuery({
    queryKey: ['settings', 'smtp'],
    queryFn: async () => {
      const data = await api.get<SmtpSettings>('/settings/smtp')
      setSmtpHost(data.host ?? '')
      setSmtpPort(String(data.port ?? 587))
      setSmtpUser(data.user ?? '')
      setSmtpPassword(data.password ?? '')
      setSmtpFrom(data.from ?? '')
      setSmtpTls(data.tls ?? true)
      return data
    },
  })

  const saveOllamaMutation = useMutation({
    mutationFn: () => api.put('/settings/ollama', { url: ollamaUrl, model: ollamaModel }),
    onSuccess: () => toast.success(t('settings.saved')),
    onError: () => toast.error(t('common.error')),
  })

  const testOllamaMutation = useMutation({
    mutationFn: () => api.post('/settings/ollama/test'),
    onSuccess: () => toast.success(t('settings.ollama.connectionSuccess')),
    onError: () => toast.error(t('settings.ollama.connectionFailed')),
  })

  const saveSmtpMutation = useMutation({
    mutationFn: () =>
      api.put('/settings/smtp', {
        host: smtpHost,
        port: parseInt(smtpPort, 10),
        user: smtpUser,
        password: smtpPassword,
        from: smtpFrom,
        tls: smtpTls,
      }),
    onSuccess: () => toast.success(t('settings.saved')),
    onError: () => toast.error(t('common.error')),
  })

  const testSmtpMutation = useMutation({
    mutationFn: () => api.post('/settings/smtp/test'),
    onSuccess: () => toast.success(t('settings.smtp.testSuccess')),
    onError: () => toast.error(t('settings.smtp.testFailed')),
  })

  async function loadModels() {
    setLoadingModels(true)
    try {
      const data = await api.get<{ models: string[] }>('/settings/ollama/models')
      setAvailableModels(data.models ?? [])
    } catch {
      toast.error(t('settings.ollama.connectionFailed'))
    } finally {
      setLoadingModels(false)
    }
  }

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('settings.title')}</h1>

      <Tabs defaultValue="ollama">
        <TabsList className="mb-6 w-full sm:w-auto">
          <TabsTrigger value="ollama" className="flex-1 sm:flex-none">{t('settings.ollama.title')}</TabsTrigger>
          <TabsTrigger value="smtp" className="flex-1 sm:flex-none">{t('settings.smtp.title')}</TabsTrigger>
        </TabsList>

        <TabsContent value="ollama">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ollama-url">{t('settings.ollama.url')}</Label>
                <Input
                  id="ollama-url"
                  type="url"
                  placeholder={t('settings.ollama.urlPlaceholder')}
                  value={ollamaUrl}
                  onChange={(e) => setOllamaUrl(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ollama-model">{t('settings.ollama.model')}</Label>
                <div className="flex gap-2">
                  <Input
                    id="ollama-model"
                    placeholder={t('settings.ollama.modelPlaceholder')}
                    value={ollamaModel}
                    onChange={(e) => setOllamaModel(e.target.value)}
                    className="flex-1"
                  />
                  <Button
                    variant="outline"
                    onClick={loadModels}
                    disabled={loadingModels}
                    className="shrink-0"
                  >
                    <ChevronDown className="h-4 w-4" />
                    {loadingModels ? t('common.loading') : t('settings.ollama.loadModels')}
                  </Button>
                </div>
                {availableModels.length > 0 && (
                  <Select value={ollamaModel} onValueChange={setOllamaModel}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('settings.ollama.modelPlaceholder')} />
                    </SelectTrigger>
                    <SelectContent>
                      {availableModels.map((model) => (
                        <SelectItem key={model} value={model}>
                          {model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              <div className="flex gap-2 pt-2">
                <Button
                  onClick={() => saveOllamaMutation.mutate()}
                  disabled={saveOllamaMutation.isPending}
                >
                  {saveOllamaMutation.isPending ? t('common.loading') : t('settings.save')}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => testOllamaMutation.mutate()}
                  disabled={testOllamaMutation.isPending}
                >
                  {testOllamaMutation.isPending ? t('common.loading') : t('settings.ollama.testConnection')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="smtp">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="smtp-host">{t('settings.smtp.host')}</Label>
                  <Input
                    id="smtp-host"
                    placeholder="smtp.example.com"
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="smtp-port">{t('settings.smtp.port')}</Label>
                  <Input
                    id="smtp-port"
                    type="number"
                    placeholder="587"
                    value={smtpPort}
                    onChange={(e) => setSmtpPort(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="smtp-user">{t('settings.smtp.user')}</Label>
                <Input
                  id="smtp-user"
                  autoComplete="username"
                  value={smtpUser}
                  onChange={(e) => setSmtpUser(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="smtp-password">{t('settings.smtp.password')}</Label>
                <Input
                  id="smtp-password"
                  type="password"
                  autoComplete="current-password"
                  value={smtpPassword}
                  onChange={(e) => setSmtpPassword(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="smtp-from">{t('settings.smtp.from')}</Label>
                <Input
                  id="smtp-from"
                  type="email"
                  placeholder="noreply@example.com"
                  value={smtpFrom}
                  onChange={(e) => setSmtpFrom(e.target.value)}
                />
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="smtp-tls">{t('settings.smtp.tls')}</Label>
                <Switch
                  id="smtp-tls"
                  checked={smtpTls}
                  onCheckedChange={setSmtpTls}
                />
              </div>

              <div className="flex gap-2 pt-2">
                <Button
                  onClick={() => saveSmtpMutation.mutate()}
                  disabled={saveSmtpMutation.isPending}
                >
                  {saveSmtpMutation.isPending ? t('common.loading') : t('settings.save')}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => testSmtpMutation.mutate()}
                  disabled={testSmtpMutation.isPending}
                >
                  {testSmtpMutation.isPending ? t('common.loading') : t('settings.smtp.sendTest')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
