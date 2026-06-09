import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import type { UserStats, UserBadge } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function Profile() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)

  const [username, setUsername] = useState(user?.username ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  useEffect(() => {
    setUsername(user?.username ?? '')
    setEmail(user?.email ?? '')
  }, [user?.username, user?.email])

  const { data: stats } = useQuery({
    queryKey: ['userStats'],
    queryFn: () => api.get<UserStats>('/users/me/stats'),
  })

  const { data: badges } = useQuery({
    queryKey: ['userBadges'],
    queryFn: () => api.get<UserBadge[]>('/users/me/badges'),
  })

  const updateProfileMutation = useMutation({
    mutationFn: (data: { username: string; email: string }) =>
      api.put('/users/me', data),
    onSuccess: (_, vars) => {
      updateUser({ username: vars.username, email: vars.email })
      toast.success(t('profile.save'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const changePasswordMutation = useMutation({
    mutationFn: (data: { currentPassword: string; newPassword: string }) =>
      api.put('/users/me/password', data),
    onSuccess: () => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      toast.success(t('profile.save'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const updatePrefsMutation = useMutation({
    mutationFn: (data: { language?: string; darkMode?: boolean }) =>
      api.put('/users/me', data),
    onSuccess: (_, vars) => {
      updateUser(vars as Parameters<typeof updateUser>[0])
    },
  })

  function handleProfileSave(e: React.FormEvent) {
    e.preventDefault()
    updateProfileMutation.mutate({ username, email })
  }

  function handlePasswordSave(e: React.FormEvent) {
    e.preventDefault()
    if (newPassword !== confirmPassword) {
      toast.error(t('auth.register.passwordMismatch'))
      return
    }
    changePasswordMutation.mutate({ currentPassword, newPassword })
  }

  function handleLanguageToggle(lang: 'en' | 'de') {
    i18n.changeLanguage(lang)
    updatePrefsMutation.mutate({ language: lang })
    updateUser({ language: lang })
  }

  function handleDarkModeToggle(checked: boolean) {
    if (checked) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    updateUser({ darkMode: checked })
    updatePrefsMutation.mutate({ darkMode: checked })
  }

  const currentLang = (i18n.language.startsWith('de') ? 'de' : 'en') as 'en' | 'de'

  return (
    <div className="p-4 md:p-6 pb-20 lg:pb-6 max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">{t('profile.title')}</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Account</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleProfileSave} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="profile-username">{t('profile.username')}</Label>
              <Input
                id="profile-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-email">{t('profile.email')}</Label>
              <Input
                id="profile-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={updateProfileMutation.isPending}>
              {updateProfileMutation.isPending ? t('common.loading') : t('profile.save')}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Password</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePasswordSave} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current-password">{t('profile.currentPassword')}</Label>
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">{t('profile.newPassword')}</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">{t('profile.confirmPassword')}</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={changePasswordMutation.isPending}>
              {changePasswordMutation.isPending ? t('common.loading') : t('profile.save')}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Preferences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label>{t('profile.language')}</Label>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleLanguageToggle('en')}
                className={`text-sm px-2 py-1 rounded transition-colors ${
                  currentLang === 'en'
                    ? 'text-primary font-semibold'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t('language.en')}
              </button>
              <span className="text-muted-foreground">|</span>
              <button
                onClick={() => handleLanguageToggle('de')}
                className={`text-sm px-2 py-1 rounded transition-colors ${
                  currentLang === 'de'
                    ? 'text-primary font-semibold'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t('language.de')}
              </button>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="dark-mode-toggle">{t('profile.darkMode')}</Label>
            <Switch
              id="dark-mode-toggle"
              checked={user?.darkMode ?? false}
              onCheckedChange={handleDarkModeToggle}
            />
          </div>
        </CardContent>
      </Card>

      {stats && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('profile.stats.title')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-3 rounded-lg bg-muted">
                <div className="text-2xl font-bold text-primary">{stats.points}</div>
                <div className="text-xs text-muted-foreground mt-1">{t('profile.stats.points')}</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted">
                <div className="text-2xl font-bold text-primary">{stats.streak}</div>
                <div className="text-xs text-muted-foreground mt-1">{t('profile.stats.streak')}</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted">
                <div className="text-2xl font-bold text-primary">{stats.sessions}</div>
                <div className="text-xs text-muted-foreground mt-1">{t('profile.stats.sessions')}</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted">
                <div className="text-2xl font-bold text-primary">
                  {stats.accuracy}%
                </div>
                <div className="text-xs text-muted-foreground mt-1">{t('profile.stats.accuracy')}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {badges && badges.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('profile.badges.title')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
              {badges.map((badge) => (
                <div
                  key={badge.id}
                  className={`flex flex-col items-center text-center p-3 rounded-lg border gap-2 ${
                    badge.earned
                      ? 'border-primary/30 bg-primary/5'
                      : 'border-border bg-muted/50 opacity-50'
                  }`}
                  title={badge.earned ? badge.description : t('profile.badges.unearned')}
                >
                  <span className="text-2xl">{badge.icon}</span>
                  <span className="text-xs font-medium leading-tight">{badge.name}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
