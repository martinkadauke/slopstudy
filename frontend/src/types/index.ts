export type TopicStatus = 'draft' | 'generating' | 'ready' | 'failed'
export type SourceType = 'file' | 'url' | 'text'
export type CardType = 'multiple_choice' | 'yes_no' | 'exact_answer' | 'exam_question'
export type StudyMode = 'multiple_choice' | 'exact_answer' | 'yes_no' | 'exam_question' | 'mixed'

export interface Topic {
  id: string
  title: string
  description?: string
  status: TopicStatus
  cardCount: number
  createdAt: string
  updatedAt: string
}

export interface Source {
  id: string
  topicId: string
  type: SourceType
  name: string
  createdAt: string
}

export interface UserStats {
  points: number
  streak: number
  sessions: number
  accuracy: number
}

export interface UserBadge {
  id: string
  name: string
  description: string
  icon: string
  earned: boolean
  earnedAt?: string
}

export interface SessionCard {
  id: string
  type: CardType
  question: string
  options?: string[]
}

export interface Session {
  id: string
  topicId: string
  mode: StudyMode
  totalCards: number
  currentIndex: number
  points: number
  skipCost: number
  skipPenalty: number
  status: 'active' | 'completed'
  currentCard: SessionCard | null
}

export interface AnswerResult {
  correct: boolean
  correctAnswer: string
  explanation?: string
  pointsDelta: number
  currentPoints: number
  llmFeedback?: string
}

export interface SessionSummaryData {
  topicId: string
  answered: number
  correct: number
  skipped: number
  accuracy: number
  pointsFromAnswers: number
  participationBonus: number
  streakBonus: number
  streakDays: number
  spentOnSkips: number
  total: number
  newBadges: UserBadge[]
}

export interface LeaderboardEntry {
  rank: number
  username: string
  points: number
  streak: number
}

export interface PointHistoryEntry {
  date: string
  points: number
}

export interface OllamaSettings {
  url: string
  model: string
}

export interface SmtpSettings {
  host: string
  port: number
  user: string
  password: string
  from: string
  tls: boolean
}
