import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/authStore'
import { AuthGuard } from '@/components/AuthGuard'
import { AppShell } from '@/components/AppShell'
import Login from '@/pages/Login'
import Register from '@/pages/Register'
import Topics from '@/pages/Topics'
import TopicDetail from '@/pages/TopicDetail'
import StudyMode from '@/pages/StudyMode'
import SessionPlayer from '@/pages/SessionPlayer'
import SessionSummary from '@/pages/SessionSummary'
import Profile from '@/pages/Profile'
import Settings from '@/pages/Settings'
import Stats from '@/pages/Stats'

export default function App() {
  const user = useAuthStore((s) => s.user)
  const { i18n } = useTranslation()

  useEffect(() => {
    if (user?.darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [user?.darkMode])

  useEffect(() => {
    if (user?.language) {
      i18n.changeLanguage(user.language)
    }
  }, [user?.language, i18n])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<AuthGuard />}>
          {/* Full-screen session routes — no nav shell */}
          <Route path="/sessions/:id" element={<SessionPlayer />} />
          <Route path="/sessions/:id/summary" element={<SessionSummary />} />
          {/* Standard shell routes */}
          <Route element={<AppShell />}>
            <Route path="/" element={<Topics />} />
            <Route path="/topics/:id" element={<TopicDetail />} />
            <Route path="/topics/:id/study" element={<StudyMode />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
