export type TopicStatus = 'draft' | 'generating' | 'ready' | 'failed'
export type SourceType = 'file' | 'url' | 'text'

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
