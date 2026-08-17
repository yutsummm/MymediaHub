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
  /** сумма по всем площадкам, где статистика собрана */
  views: number
  reactions: number
  comments: number
  shares: number
  /** разбивка по площадкам; пусто — по посту ничего не собрано */
  stats?: PostPlatformStat[]
  publish_error?: string | null
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

/**
 * Задача публикации. Публикация асинхронная: ручка ставит пост в очередь и
 * сразу отвечает, отправкой занимается фоновый воркер. Раньше загрузка видео
 * в ВК шла прямо внутри запроса и упиралась в таймаут прокси.
 */
export interface PublishJob {
  id: number
  post_id: number
  state: 'queued' | 'running' | 'done' | 'failed' | 'none'
  error: string | null
  /** JSON с результатом по площадкам, заполняется по завершении */
  result: string | null
  attempts: number
  created_at: string | null
  finished_at: string | null
}

/** Разобранный результат задачи — то, что раньше приходило прямо из ручки */
export interface PublishOutcome {
  vk_post_id?: number | null
  vk_error?: string | null
  vk_photo_errors?: string[] | null
  tg_message_ids?: number[] | null
  tg_error?: string | null
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
  /** null — просмотры ни по одной площадке не собирали, среднего не существует */
  avg_views: number | null
  /** null — считать вовлечённость не из чего (нет просмотров), а не «ноль процентов» */
  engagement_rate: number | null
  top_posts: Post[]
  platform_stats: PlatformStat[]
}

export interface PostPlatformStat {
  platform: string
  /** null — по этой площадке счётчик не собирали (ноль означал бы «собрали, там ноль») */
  views: number | null
  reactions: number | null
  comments: number | null
  shares: number | null
  updated_at: string | null
  available: boolean
}

export interface PlatformStat {
  platform: string
  /** сколько постов ушло на площадку */
  count: number
  /** по скольким из них статистика собрана */
  collected: number
  /** null — по этой площадке данных нет (см. stats_available) */
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

/** Сведения о странице списка: по ним рисуется навигация */
export interface PageMeta {
  total: number
  limit: number
  offset: number
  has_more: boolean
}

/** Активный вход в аккаунт */
export interface SessionInfo {
  created_at: string
  last_seen_at: string | null
  expires_at: string
  ip: string | null
  user_agent: string | null
  current: boolean
}


/** Смета удаления группы: что именно исчезнет. Считает сервер. */
export interface GroupDeletionPreview {
  name: string
  /** Фраза, которую нужно набрать для подтверждения — название группы. */
  confirm_with: string
  posts: number
  published_posts: number
  members: number
  invites: number
  volunteer_media: number
  notifications: number
  integrations: number
}

/** Смета удаления пользователя. Посты остаются, у них пропадает автор. */
export interface UserDeletionPreview {
  name: string
  email: string
  confirm_with: string
  posts_kept: number
  groups: number
  volunteer_media: number
  sessions: number
  /** Группы, где он единственный администратор — ими станет некому управлять. */
  sole_admin_of: string[]
}

/** Запись журнала действий. */
export interface AuditEntry {
  id: number
  created_at: string
  actor_id: number | null
  actor_email: string | null
  action: string
  object_type: string | null
  object_id: number | null
  object_label: string | null
  group_id: number | null
  details: Record<string, unknown> | null
  ip: string | null
}
