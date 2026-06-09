import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { AuthUser } from '@/store/authStore'

interface RegisterResponse {
  token: string
  user: AuthUser
}

interface FieldErrors {
  email?: string[]
  username?: string[]
  password?: string[]
}

export default function Register() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [generalError, setGeneralError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFieldErrors({})
    setGeneralError('')

    if (password !== confirmPassword) {
      setFieldErrors({ password: [t('auth.register.passwordMismatch')] })
      return
    }

    setLoading(true)
    try {
      const data = await api.post<RegisterResponse>('/auth/register', {
        email,
        username,
        password,
      })
      login(data.token, data.user)
      navigate('/')
    } catch (err: unknown) {
      const error = err as { status?: number; errors?: FieldErrors; message?: string }
      if (error.status === 422 && error.errors) {
        setFieldErrors(error.errors)
      } else {
        setGeneralError(error.message ?? t('common.error'))
      }
    } finally {
      setLoading(false)
    }
  }

  function switchLang(lang: string) {
    i18n.changeLanguage(lang)
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <BookOpen className="h-8 w-8 text-primary" />
          <span className="font-bold text-2xl">SlopStudy</span>
        </div>

        <div className="flex justify-center gap-2 mb-6">
          <button
            onClick={() => switchLang('en')}
            className={`text-sm px-2 py-1 rounded transition-colors ${
              i18n.language === 'en'
                ? 'text-primary font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('language.en')}
          </button>
          <span className="text-muted-foreground">|</span>
          <button
            onClick={() => switchLang('de')}
            className={`text-sm px-2 py-1 rounded transition-colors ${
              i18n.language.startsWith('de')
                ? 'text-primary font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t('language.de')}
          </button>
        </div>

        <Card>
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl text-center">{t('auth.register.title')}</CardTitle>
            <CardDescription className="text-center">{t('auth.register.subtitle')}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {generalError && (
                <p className="text-sm text-destructive text-center">{generalError}</p>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">{t('auth.register.email')}</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                {fieldErrors.email?.map((err) => (
                  <p key={err} className="text-xs text-destructive">{err}</p>
                ))}
              </div>

              <div className="space-y-2">
                <Label htmlFor="username">{t('auth.register.username')}</Label>
                <Input
                  id="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
                {fieldErrors.username?.map((err) => (
                  <p key={err} className="text-xs text-destructive">{err}</p>
                ))}
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">{t('auth.register.password')}</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                {fieldErrors.password?.map((err) => (
                  <p key={err} className="text-xs text-destructive">{err}</p>
                ))}
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword">{t('auth.register.confirmPassword')}</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? t('common.loading') : t('auth.register.submit')}
              </Button>
            </form>

            <p className="mt-4 text-center text-sm text-muted-foreground">
              {t('auth.register.hasAccount')}{' '}
              <Link to="/login" className="text-primary hover:underline font-medium">
                {t('auth.register.login')}
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
