export interface User {
  id: number
  name: string
  email: string
  role: 'admin' | 'editor' | 'volunteer'
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
  location_address: string | null
  location_lat: number | null
  location_lng: number | null
  vk_post_id?: string | null
  tg_message_ids?: number[]
  vk_stats_updated_at?: string | null
}

/**
 * Ответ ручек публикации: сам пост плюс результат отправки в VK и Telegram.
 * Поля необязательные — приходят только когда платформа реально задействована.
 */
export interface PublishResult extends Post {
  vk_error?: string
  vk_photo_errors?: string[]
  tg_error?: string
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
  /** null — статистика по этой площадке не собирается (см. stats_available) */
  views: number | null
  reactions: number | null
  stats_available: boolean
}

export interface TimelinePoint {
  date: string
  label: string
  views: number
  reactions: number
  posts: number
}

export interface YouthCenter {
  id: number
  name: string
  address: string
  coordinates?: [number, number]
  lat: number
  lon: number
  distance_km?: number
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

export interface TgSettings {
  connected: boolean
  chat_id?: string
  chat_title?: string
  connected_at?: string
}

export type GroupRole = 'admin' | 'editor' | 'volunteer'

export interface Group {
  id: number
  name: string
  description: string
  avatar: string
  role: GroupRole
  created_by?: number
  created_at: string
}

export interface GroupMember {
  id: number
  name: string
  email: string
  avatar: string
  role: GroupRole
  joined_at: string
}

export interface InviteLink {
  id: number
  token: string
  role: GroupRole
  expires_at: string
  used_count: number
  max_uses: number | null
  created_at?: string
}

export interface InvitePreview {
  group_id: number
  group_name: string
  group_description: string
  role: GroupRole
  expires_at: string
}

export interface VolunteerMedia {
  id: number
  user_id: number
  user_name?: string
  group_id: number
  event_name: string
  media: MediaItem[]
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}
