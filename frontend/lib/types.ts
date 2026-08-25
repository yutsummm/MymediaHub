export interface User {
  id: number
  name: string
  email: string
  /**
   * Глобальная роль — про администрирование системы, и только. Права на
   * контент живут в GroupRole. Здесь долго стояло 'admin' | 'editor' |
   * 'volunteer' — набор, которого после разделения систем ролей не
   * существует; по нему в редакторе была закрыта кнопка медиатеки, и видели
   * её одни глобальные администраторы.
   */
  role: 'admin' | 'member'
  avatar: string
  created_at: string
}

export interface MediaItem {
  url: string
  type: 'image' | 'video' | 'doc'
  filename: string
}

export type PostStatus = 'draft' | 'on_review' | 'scheduled' | 'published'

export interface Post {
  id: number
  title: string
  content: string
  status: PostStatus
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
  /** Согласование: когда отправлен, кто и когда посмотрел, что сказал при возврате */
  submitted_at?: string | null
  reviewed_at?: string | null
  reviewed_by?: number | null
  review_comment?: string | null
  /**
   * Свой текст под площадку: {"telegram": "..."}. Пустое значение означает
   * «взять общий текст» — так же, как было до появления переопределений.
   */
  content_overrides?: Record<string, string>
  /** Ссылка уходит первым комментарием, а не в тело записи (только ВКонтакте) */
  first_comment?: string | null
  vk_comment_id?: string | null
  /** Когда убрать запись из соцсети и когда убрали на самом деле */
  auto_delete_at?: string | null
  removed_at?: string | null
  remove_error?: string | null
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
  on_review: number
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
  /** Посты выходят только после визы администратора группы */
  require_approval?: boolean
  /** Размечать ли ссылки UTM-метками на выпуске */
  utm_enabled?: boolean
  /** Подстановки {{ключ}} в тексте поста */
  variables?: Record<string, string>
  /** Именованные наборы хештегов */
  hashtag_sets?: HashtagSet[]
  /** За сколько часов положено ответить на обращение под публикацией */
  reply_sla_hours?: number
  role: GroupRole
  created_by?: number
  created_at: string
}

export interface HashtagSet {
  name: string
  tags: string
}

/**
 * Окно расписания публикаций. weekday: 0 — понедельник, как у
 * datetime.weekday() на бэкенде: считать дни недели двумя способами нельзя.
 */
export interface PublishingSlot {
  id?: number
  weekday: number
  at: string
  weekday_label?: string
}

/** Событие в истории поста: создание, согласование, публикация, снятие. */
export interface PostHistoryEvent {
  at: string | null
  action: string
  label: string
  actor: string | null
  details: string | null
}

/**
 * Обращение под публикацией. minutes_left — сколько осталось до срока ответа;
 * отрицательное значит просрочено, null — у отвеченных, где срок уже неприменим.
 */
export interface PostComment {
  id: number
  post_id: number
  post_title: string | null
  platform: string
  author_name: string | null
  text: string
  created_at: string | null
  answered_at: string | null
  due_at: string | null
  minutes_left: number | null
  overdue: boolean
}

export interface CommentsSummary {
  pending: number
  overdue: number
  sla_hours: number
}

/** Шаг начала работы. Состояние считается по данным, а не хранится флагом. */
export interface OnboardingStep {
  key: string
  title: string
  hint: string
  done: boolean
  href: string
  optional: boolean
}

export interface OnboardingProgress {
  steps: OnboardingStep[]
  done: number
  total: number
  complete: boolean
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

/**
 * Карточка медиатеки: файл, уже загруженный в группе, и откуда он взялся.
 * Источника два — одобренные материалы волонтёров и файлы из прошлых постов.
 */
export interface MediaLibraryItem extends MediaItem {
  source: 'volunteer' | 'post'
  /** название мероприятия либо заголовок поста, откуда файл */
  label: string
  author: string | null
  at: string | null
}
