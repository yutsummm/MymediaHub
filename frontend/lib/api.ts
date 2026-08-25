// На проде используем относительные URL — Next.js rewrites проксирует /api/* на бэк
// (см. next.config.mjs / BACKEND_URL). Локально NEXT_PUBLIC_API_URL=http://localhost:8000.
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

/**
 * Токен по умолчанию берётся прямо из localStorage, а не отдаётся как null.
 *
 * `setTokenGetter` вызывает AuthContext из `useEffect`, а React выполняет
 * эффекты детей раньше эффектов родителя. Поэтому GroupContext и уведомления
 * успевали сходить за данными до того, как геттер вообще был установлен:
 * запрос уходил без заголовка, получал 401 и больше не повторялся — деревья
 * зависимостей на это не реагируют. Наружу это выглядело так, что человек с
 * группами при каждой перезагрузке видел «Создайте вашу первую группу» и
 * пустые уведомления.
 *
 * Запасной источник снимает зависимость от порядка эффектов целиком: где бы
 * ни оказался вызов, токен лежит в том же месте, куда его положил вход.
 * После выхода ключ удаляется, поэтому запасной путь вернёт null сам.
 */
function tokenFromStorage(): string | null {
  try {
    return localStorage.getItem('mediahub_token')
  } catch {
    return null
  }
}

let _getToken: () => string | null = tokenFromStorage
let _onUnauthorized: () => void = () => {}

export function setTokenGetter(fn: () => string | null) {
  _getToken = () => fn() ?? tokenFromStorage()
}
export function setUnauthorizedHandler(fn: () => void) { _onUnauthorized = fn }

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${BASE}${path}`
  const token = _getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (init.headers instanceof Headers) {
    init.headers.forEach((v, k) => { headers[k] = v })
  } else if (init.headers) {
    Object.assign(headers, init.headers)
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  let res: Response
  try {
    res = await fetch(url, {
      headers,
      ...init,
    })
  } catch (e) {
    throw new Error(`Сеть недоступна (${url}): ${(e as Error).message}`)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail: string | undefined
    try { detail = JSON.parse(text)?.detail } catch {}
    // Only auto-logout when we sent a valid token but backend rejected it (expired/invalid)
    if (res.status === 401 && token) {
      _onUnauthorized()
    }
    throw new Error(detail ?? `${res.status} ${res.statusText} — ${url}`)
  }
  return res.json()
}

const body = (data: unknown) => JSON.stringify(data)

/**
 * Скачивает файл, отданный API. Имя берём из Content-Disposition — сервер
 * называет файл по-русски и по периоду, а придумывать имя заново на клиенте
 * значило бы разойтись с ним при первой же правке.
 */
async function download(path: string, fallbackName: string): Promise<void> {
  const token = _getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { headers })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail: string | undefined
    try { detail = JSON.parse(text)?.detail } catch {}
    throw new Error(detail ?? `Не удалось получить файл: ${res.status}`)
  }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  const cd = res.headers.get('content-disposition') ?? ''
  const match = cd.match(/filename\*=UTF-8''(.+)/)
  a.download = match ? decodeURIComponent(match[1]) : fallbackName
  a.click()
  URL.revokeObjectURL(a.href)
}

/**
 * Ждёт, пока воркер разберёт задачу публикации.
 *
 * Отправка в соцсети идёт вне HTTP-запроса, поэтому результат забираем
 * опросом. Загрузка видео в ВК может занять минуты — отсюда щедрый предел
 * ожидания; по его истечении задача не отменяется, а продолжает выполняться,
 * и её состояние всегда можно посмотреть заново.
 */
export async function waitForPublish(
  jobId: number,
  { intervalMs = 1200, timeoutMs = 5 * 60_000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<import('./types').PublishJob> {
  const until = Date.now() + timeoutMs
  let job = await api.getPublishJob(jobId)
  while ((job.state === 'queued' || job.state === 'running') && Date.now() < until) {
    await new Promise(r => setTimeout(r, intervalMs))
    job = await api.getPublishJob(jobId)
  }
  return job
}

/** Разбирает результат задачи в привычный вид «что ушло, что нет» */
export function publishOutcome(job: import('./types').PublishJob): import('./types').PublishOutcome {
  if (!job.result) return {}
  try { return JSON.parse(job.result) } catch { return {} }
}

export const api = {
  login: (email: string, password: string) =>
    req<{ user: import('./types').User; token: string }>('/api/auth/login', {
      method: 'POST', body: body({ email, password }),
    }),
  // Регистрация в два шага: register только шлёт код на почту, аккаунт создаёт
  // verifyEmail. inviteToken — регистрация по ссылке-приглашению; без него новый
  // пользователь не попадает ни в одну существующую группу.
  register: (name: string, email: string, password: string, inviteToken?: string | null) =>
    req<{ status: string; email: string }>('/api/auth/register', {
      method: 'POST',
      body: body(inviteToken ? { name, email, password, invite_token: inviteToken } : { name, email, password }),
    }),
  verifyEmail: (email: string, code: string) =>
    req<{
      user: import('./types').User
      token: string
      groups: import('./types').Group[]
      invite_error: string | null
    }>('/api/auth/verify-email', { method: 'POST', body: body({ email, code }) }),
  resendCode: (email: string) =>
    req<{ status: string }>('/api/auth/resend-code', { method: 'POST', body: body({ email }) }),
  // Настоящий выход: гасит токен на сервере. Раньше выход был только на
  // клиенте — приложение забывало токен, а сам токен жил ещё до 72 часов.
  logout: () => req<{ status: string }>('/api/auth/logout', { method: 'POST' }),
  logoutEverywhere: () =>
    req<{ status: string; sessions_revoked: number }>('/api/auth/logout-all', { method: 'POST' }),
  getSessions: () =>
    req<{ sessions: import('./types').SessionInfo[] }>('/api/auth/sessions'),
  forgotPassword: (email: string) =>
    req<{ status: string }>('/api/auth/forgot-password', {
      method: 'POST', body: body({ email }),
    }),
  resetPassword: (email: string, code: string, new_password: string) =>
    req<{ status: string }>('/api/auth/reset-password', {
      method: 'POST', body: body({ email, code, new_password }),
    }),

  getUsers: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ users: import('./types').User[] } & import('./types').PageMeta>(`/api/users${qs}`)
  },
  updateUserRole: (id: number, role: string) =>
    req<import('./types').User>(`/api/users/${id}/role`, { method: 'PUT', body: body({ role }) }),
  createUser: (name: string, email: string, role: string, password: string) =>
    req<import('./types').User>('/api/users', { method: 'POST', body: body({ name, email, role, password }) }),
  // Удаление требует подтверждения: confirm — точная почта пользователя.
  // Без него сервер отвечает 409 и объясняет, что именно на кону.
  getUserDeletionPreview: (id: number) =>
    req<import('./types').UserDeletionPreview>(`/api/users/${id}/deletion-preview`),
  deleteUser: (id: number, confirm: string) =>
    req<{ ok: boolean }>(`/api/users/${id}?confirm=${encodeURIComponent(confirm)}`, { method: 'DELETE' }),

  getPosts: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ posts: import('./types').Post[] } & import('./types').PageMeta>(`/api/posts${qs}`)
  },
  getPost: (id: number) => req<import('./types').Post>(`/api/posts/${id}`),
  createPost: (data: unknown) =>
    req<import('./types').Post>('/api/posts', { method: 'POST', body: body(data) }),
  updatePost: (id: number, data: unknown) =>
    req<import('./types').Post>(`/api/posts/${id}`, { method: 'PUT', body: body(data) }),
  deletePost: (id: number) => req<{ ok: boolean }>(`/api/posts/${id}`, { method: 'DELETE' }),
  // Ставит пост в очередь и сразу отвечает. Дождаться результата — waitForPublish.
  publishPost: (id: number) =>
    req<import('./types').PublishJob>(`/api/posts/${id}/publish`, { method: 'POST' }),
  getPublishJob: (jobId: number) =>
    req<import('./types').PublishJob>(`/api/publish-jobs/${jobId}`),
  getPostPublishJob: (postId: number) =>
    req<import('./types').PublishJob>(`/api/posts/${postId}/publish-job`),

  getCalendar: (start: string, end: string) =>
    req<import('./types').Post[]>(`/api/calendar?start=${start}&end=${end}`),
  getYouthCenters: (lat: number, lon: number) =>
    req<import('./types').YouthCenter[]>(`/api/youth-centers?lat=${lat}&lon=${lon}`),

  getTemplates: () => req<import('./types').Template[]>('/api/templates'),
  generateText: (template_type: string, fields: Record<string, string>) =>
    req<{ text: string; title: string }>('/api/generate-text', {
      method: 'POST', body: body({ template_type, fields }),
    }),

  enhanceText: (text: string, mode: string) =>
    req<{ text: string }>('/api/ai-enhance', {
      method: 'POST', body: body({ text, mode }),
    }),

  getAnalyticsSummary: () => req<import('./types').AnalyticsSummary>('/api/analytics/summary'),
  getTimeline: (period: string) =>
    req<import('./types').TimelinePoint[]>(`/api/analytics/timeline?period=${period}`),
  exportAnalytics: (startDate: string, endDate: string): Promise<void> =>
    download(`/api/analytics/export?start_date=${startDate}&end_date=${endDate}`, 'аналитика.xlsx'),
  // Отчёт для учредителя — другой документ и другой язык, чем выгрузка аналитики
  downloadReport: (startDate: string, endDate: string): Promise<void> =>
    download(`/api/analytics/report?start_date=${startDate}&end_date=${endDate}`, 'отчёт.xlsx'),

  getNotifications: () =>
    req<{ items: import('./types').Notification[]; total: number }>('/api/notifications'),
  markRead: (id: number) => req<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: 'PUT' }),

  uploadFile: async (file: File): Promise<import('./types').MediaItem> => {
    const form = new FormData()
    form.append('file', file)
    const url = `${BASE}/api/upload`
    // Content-Type не задаём — его выставит браузер вместе с boundary для FormData
    const token = _getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    let res: Response
    try {
      res = await fetch(url, { method: 'POST', body: form, headers })
    } catch (e) {
      throw new Error(`Сеть недоступна: ${(e as Error).message}`)
    }
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      let detail: string | undefined
      try { detail = JSON.parse(text)?.detail } catch {}
      throw new Error(detail ?? `${res.status} ${res.statusText}`)
    }
    return res.json()
  },

  getVkSettings: () => req<import('./types').VkSettings>('/api/settings/vk'),
  saveVkSettings: (group_id: string, access_token: string) =>
    req<import('./types').VkSettings>('/api/settings/vk', {
      method: 'POST', body: body({ group_id, access_token }),
    }),
  deleteVkSettings: () => req<{ connected: boolean }>('/api/settings/vk', { method: 'DELETE' }),
  vkOAuthExchange: (app_id: string, app_secret: string, code: string, group_id: string) =>
    req<import('./types').VkSettings>('/api/vk/oauth-exchange', {
      method: 'POST', body: body({ app_id, app_secret, code, group_id }),
    }),

  getTgSettings: () => req<import('./types').TgSettings>('/api/settings/telegram'),
  saveTgSettings: (bot_token: string, chat_id: string) =>
    req<import('./types').TgSettings>('/api/settings/telegram', {
      method: 'POST', body: body({ bot_token, chat_id }),
    }),
  deleteTgSettings: () => req<{ connected: boolean }>('/api/settings/telegram', { method: 'DELETE' }),

  // Groups
  getGroups: () => req<import('./types').Group[]>('/api/groups'),
  createGroup: (name: string, description?: string) =>
    req<import('./types').Group>('/api/groups', {
      method: 'POST', body: body({ name, description: description || '' }),
    }),
  getGroup: (groupId: number) => req<import('./types').Group>(`/api/groups/${groupId}`),
  updateGroup: (groupId: number, data: {
    name?: string; description?: string; avatar?: string
    require_approval?: boolean; utm_enabled?: boolean; reply_sla_hours?: number
    variables?: Record<string, string>
    hashtag_sets?: import('./types').HashtagSet[]
  }) =>
    req<import('./types').Group>(`/api/groups/${groupId}`, {
      method: 'PUT', body: body(data),
    }),
  // confirm — точное название группы, см. getUserDeletionPreview.
  getGroupDeletionPreview: (groupId: number) =>
    req<import('./types').GroupDeletionPreview>(`/api/groups/${groupId}/deletion-preview`),
  deleteGroup: (groupId: number, confirm: string) =>
    req<{ ok: boolean }>(`/api/groups/${groupId}?confirm=${encodeURIComponent(confirm)}`, { method: 'DELETE' }),

  getAuditLog: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ items: import('./types').AuditEntry[] } & import('./types').PageMeta>(`/api/audit${qs}`)
  },
  getGroupAuditLog: (groupId: number, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ items: import('./types').AuditEntry[] } & import('./types').PageMeta>(
      `/api/groups/${groupId}/audit${qs}`,
    )
  },

  // Group members
  getGroupMembers: (groupId: number) =>
    req<import('./types').GroupMember[]>(`/api/groups/${groupId}/members`),
  updateMemberRole: (groupId: number, userId: number, role: string) =>
    req<import('./types').GroupMember>(`/api/groups/${groupId}/members/${userId}/role`, {
      method: 'PUT', body: body({ role }),
    }),
  removeGroupMember: (groupId: number, userId: number) =>
    req<{ ok: boolean }>(`/api/groups/${groupId}/members/${userId}`, { method: 'DELETE' }),

  // Invite links
  createInviteLink: (groupId: number, role?: string, expires_hours?: number, max_uses?: number | null) =>
    req<import('./types').InviteLink>(`/api/groups/${groupId}/invites`, {
      method: 'POST', body: body({ role: role || 'editor', expires_hours: expires_hours || 24, max_uses }),
    }),
  getInviteLinks: (groupId: number) =>
    req<import('./types').InviteLink[]>(`/api/groups/${groupId}/invites`),
  revokeInviteLink: (groupId: number, linkId: number) =>
    req<{ ok: boolean }>(`/api/groups/${groupId}/invites/${linkId}`, { method: 'DELETE' }),
  getInvitePreview: (token: string) =>
    req<import('./types').InvitePreview>(`/api/invites/${token}`),
  acceptInvite: (token: string) =>
    req<import('./types').Group>(`/api/invites/${token}/accept`, { method: 'POST' }),

  // Volunteer media
  getVolunteerMedia: (groupId: number, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ items: import('./types').VolunteerMedia[]; total: number }>(`/api/groups/${groupId}/volunteer-media${qs}`)
  },
  createVolunteerMedia: (groupId: number, data: { event_name: string; media: import('./types').MediaItem[] }) =>
    req<import('./types').VolunteerMedia>(`/api/groups/${groupId}/volunteer-media`, {
      method: 'POST', body: body(data),
    }),
  deleteVolunteerMedia: (groupId: number, id: number) =>
    req<{ ok: boolean }>(`/api/groups/${groupId}/volunteer-media/${id}`, { method: 'DELETE' }),
  updateVolunteerMediaStatus: (groupId: number, id: number, status: string) =>
    req<import('./types').VolunteerMedia>(`/api/groups/${groupId}/volunteer-media/${id}/status`, {
      method: 'PUT', body: body({ status }),
    }),

  // Group-scoped posts
  getGroupPosts: (groupId: number, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ posts: import('./types').Post[] } & import('./types').PageMeta>(`/api/groups/${groupId}/posts${qs}`)
  },
  getGroupPost: (groupId: number, postId: number) =>
    req<import('./types').Post>(`/api/groups/${groupId}/posts/${postId}`),
  createGroupPost: (groupId: number, data: unknown) =>
    req<import('./types').Post>(`/api/groups/${groupId}/posts`, {
      method: 'POST', body: body(data),
    }),
  updateGroupPost: (groupId: number, postId: number, data: unknown) =>
    req<import('./types').Post>(`/api/groups/${groupId}/posts/${postId}`, {
      method: 'PUT', body: body(data),
    }),
  deleteGroupPost: (groupId: number, postId: number) =>
    req<{ ok: boolean }>(`/api/groups/${groupId}/posts/${postId}`, { method: 'DELETE' }),
  publishGroupPost: (groupId: number, postId: number) =>
    req<import('./types').PublishJob>(`/api/groups/${groupId}/posts/${postId}/publish`, { method: 'POST' }),

  // Согласование. Отдельные ручки, а не смена статуса через PUT: у перехода
  // есть побочные действия — уведомления, журнал, выпуск поста, — и прятать
  // их внутрь обновления поля значило бы, что любой PUT рассылает уведомления.
  submitGroupPost: (groupId: number, postId: number) =>
    req<{ status: string }>(`/api/groups/${groupId}/posts/${postId}/submit`, { method: 'POST' }),
  approveGroupPost: (groupId: number, postId: number) =>
    req<{ status: string; job: import('./types').PublishJob | null }>(
      `/api/groups/${groupId}/posts/${postId}/approve`, { method: 'POST' }),
  rejectGroupPost: (groupId: number, postId: number, comment: string) =>
    req<{ status: string }>(`/api/groups/${groupId}/posts/${postId}/reject`, {
      method: 'POST', body: body({ comment }),
    }),

  // Расписание публикаций: правится целиком, как сетка недели
  getSlots: (groupId: number) =>
    req<{ slots: import('./types').PublishingSlot[] }>(`/api/groups/${groupId}/slots`),
  saveSlots: (groupId: number, slots: import('./types').PublishingSlot[]) =>
    req<{ slots: import('./types').PublishingSlot[] }>(`/api/groups/${groupId}/slots`, {
      method: 'PUT',
      body: body({ slots: slots.map(s => ({ weekday: s.weekday, at: s.at })) }),
    }),
  // Ближайшее свободное окно — показываем до постановки в очередь, чтобы
  // человек заранее видел, когда пост выйдет
  getNextSlot: (groupId: number) =>
    req<{ at: string }>(`/api/groups/${groupId}/slots/next`),
  // Время считает сервер по расписанию группы: держать копию правил на
  // клиенте значило бы однажды с ними разойтись
  queueGroupPost: (groupId: number, postId: number, autoDeleteAt?: string | null) =>
    req<import('./types').Post & { queued: boolean }>(
      `/api/groups/${groupId}/posts/${postId}/queue`, {
        method: 'POST', body: body({ auto_delete_at: autoDeleteAt ?? null }),
      }),

  getPostHistory: (postId: number) =>
    req<{ events: import('./types').PostHistoryEvent[] }>(`/api/posts/${postId}/history`),

  // Обращения под публикациями и срок ответа на них
  getComments: (groupId: number, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ items: import('./types').PostComment[]; sla_hours: number }
      & import('./types').PageMeta>(`/api/groups/${groupId}/comments${qs}`)
  },
  getCommentsSummary: (groupId: number) =>
    req<import('./types').CommentsSummary>(`/api/groups/${groupId}/comments/summary`),
  replyToComment: (groupId: number, commentId: number, text: string) =>
    req<{ ok: boolean; answered_at: string }>(
      `/api/groups/${groupId}/comments/${commentId}/reply`, {
        method: 'POST', body: body({ text }),
      }),

  // Что в группе ещё не настроено. Считается на сервере по данным.
  getOnboarding: (groupId: number) =>
    req<import('./types').OnboardingProgress>(`/api/groups/${groupId}/onboarding`),

  // Медиатека: одобренные материалы волонтёров плюс файлы из прошлых постов
  getMediaLibrary: (groupId: number, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ items: import('./types').MediaLibraryItem[] } & import('./types').PageMeta>(
      `/api/groups/${groupId}/media-library${qs}`)
  },

  // Group-scoped settings
  getGroupVkSettings: (groupId: number) =>
    req<import('./types').VkSettings>(`/api/groups/${groupId}/settings/vk`),
  saveGroupVkSettings: (groupId: number, group_id: string, access_token: string) =>
    req<import('./types').VkSettings>(`/api/groups/${groupId}/settings/vk`, {
      method: 'POST', body: body({ group_id, access_token }),
    }),
  deleteGroupVkSettings: (groupId: number) =>
    req<{ connected: boolean }>(`/api/groups/${groupId}/settings/vk`, { method: 'DELETE' }),

  getGroupTgSettings: (groupId: number) =>
    req<import('./types').TgSettings>(`/api/groups/${groupId}/settings/telegram`),
  saveGroupTgSettings: (groupId: number, bot_token: string, chat_id: string) =>
    req<import('./types').TgSettings>(`/api/groups/${groupId}/settings/telegram`, {
      method: 'POST', body: body({ bot_token, chat_id }),
    }),
  deleteGroupTgSettings: (groupId: number) =>
    req<{ connected: boolean }>(`/api/groups/${groupId}/settings/telegram`, { method: 'DELETE' }),

  syncVkStats: () =>
    req<{ synced: number; message: string }>('/api/posts/sync-vk-stats', { method: 'POST' }),

  // Group-scoped analytics
  getGroupAnalyticsSummary: (groupId: number) =>
    req<import('./types').AnalyticsSummary>(`/api/groups/${groupId}/analytics/summary`),
  getGroupTimeline: (groupId: number, period: string) =>
    req<import('./types').TimelinePoint[]>(`/api/groups/${groupId}/analytics/timeline?period=${period}`),
  exportGroupAnalytics: (groupId: number, startDate: string, endDate: string): Promise<void> =>
    download(`/api/groups/${groupId}/analytics/export?start_date=${startDate}&end_date=${endDate}`,
      'аналитика.xlsx'),
  downloadGroupReport: (groupId: number, startDate: string, endDate: string): Promise<void> =>
    download(`/api/groups/${groupId}/analytics/report?start_date=${startDate}&end_date=${endDate}`,
      'отчёт.xlsx'),

  // Group-scoped sync VK stats
  syncGroupVkStats: (groupId: number) =>
    req<{ synced: number; message: string }>(`/api/groups/${groupId}/posts/sync-vk-stats`, { method: 'POST' }),
}
