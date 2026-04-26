export interface User {
  id: number
  name: string
  email: string
  role: 'admin' | 'editor' | 'observer'
  avatar: string
  created_at: string
}

export interface MediaItem {
  url: string
  type: 'image' | 'video' | 'doc'
  filename: string
}

export interface Post {
  id: number
  title: string
  content: string
  status: 'draft' | 'scheduled' | 'published'
  platforms: string[]
  tags: string[]
  scheduled_at: string | null
  published_at: string | null
  views: number
  reactions: number
  comments: number
  shares: number
  author_id: number
  author_name?: string
  template_type: string | null
  created_at: string
  media: MediaItem[]
}

export interface TemplateField {
  key: string
  label: string
  placeholder: string
}

export interface Template {
  id: number
  name: string
  type: string
  description: string
  fields: TemplateField[]
  template_text: string
}

export interface AnalyticsSummary {
  total_posts: number
  published: number
  scheduled: number
  drafts: number
  total_views: number
  total_reactions: number
  total_comments: number
  total_shares: number
  avg_views: number
  engagement_rate: number
  top_posts: Post[]
  platform_stats: PlatformStat[]
}

export interface PlatformStat {
  platform: string
  count: number
  views: number
  reactions: number
}

export interface TimelinePoint {
  date: string
  label: string
  views: number
  reactions: number
  posts: number
}

export interface Notification {
  id: number
  user_id: number
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
  is_read: number
  created_at: string
}

export interface VkSettings {
  connected: boolean
  group_id?: string
  group_name?: string
  connected_at?: string
}
