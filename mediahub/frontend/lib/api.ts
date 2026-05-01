// На проде используем относительные URL — Next.js rewrites проксирует /api/* на бэк
// (см. next.config.mjs / BACKEND_URL). Локально NEXT_PUBLIC_API_URL=http://localhost:8000.
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

let _getToken: () => string | null = () => null
let _onUnauthorized: () => void = () => {}

export function setTokenGetter(fn: () => string | null) { _getToken = fn }
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

export const api = {
  login: (email: string, password: string) =>
    req<{ user: import('./types').User; token: string }>('/api/auth/login', {
      method: 'POST', body: body({ email, password }),
    }),
  register: (name: string, email: string, password: string) =>
    req<{ user: import('./types').User; token: string }>('/api/auth/register', {
      method: 'POST', body: body({ name, email, password }),
    }),

  getUsers: () => req<import('./types').User[]>('/api/users'),
  updateUserRole: (id: number, role: string) =>
    req<import('./types').User>(`/api/users/${id}/role`, { method: 'PUT', body: body({ role }) }),
  createUser: (name: string, email: string, role: string, password: string) =>
    req<import('./types').User>('/api/users', { method: 'POST', body: body({ name, email, role, password }) }),
  deleteUser: (id: number) => req<{ ok: boolean }>(`/api/users/${id}`, { method: 'DELETE' }),

  getPosts: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ posts: import('./types').Post[]; total: number }>(`/api/posts${qs}`)
  },
  getPost: (id: number) => req<import('./types').Post>(`/api/posts/${id}`),
  createPost: (data: unknown) =>
    req<import('./types').Post>('/api/posts', { method: 'POST', body: body(data) }),
  updatePost: (id: number, data: unknown) =>
    req<import('./types').Post>(`/api/posts/${id}`, { method: 'PUT', body: body(data) }),
  deletePost: (id: number) => req<{ ok: boolean }>(`/api/posts/${id}`, { method: 'DELETE' }),
  publishPost: (id: number) =>
    req<import('./types').Post>(`/api/posts/${id}/publish`, { method: 'POST' }),

  getCalendar: (start: string, end: string) =>
    req<import('./types').Post[]>(`/api/calendar?start=${start}&end=${end}`),

  getTemplates: () => req<import('./types').Template[]>('/api/templates'),
  generateText: (template_type: string, fields: Record<string, string>) =>
    req<{ text: string; title: string }>('/api/generate-text', {
      method: 'POST', body: body({ template_type, fields }),
    }),

  enhanceText: (text: string, mode: 'creative' | 'russify') =>
    req<{ text: string }>('/api/ai-enhance', {
      method: 'POST', body: body({ text, mode }),
    }),

  getAnalyticsSummary: () => req<import('./types').AnalyticsSummary>('/api/analytics/summary'),
  getTimeline: (period: string) =>
    req<import('./types').TimelinePoint[]>(`/api/analytics/timeline?period=${period}`),

  getNotifications: (user_id?: number) =>
    req<import('./types').Notification[]>(`/api/notifications${user_id ? `?user_id=${user_id}` : ''}`),
  markRead: (id: number) => req<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: 'PUT' }),

  uploadFile: async (file: File): Promise<import('./types').MediaItem> => {
    const form = new FormData()
    form.append('file', file)
    const url = `${BASE}/api/upload`
    let res: Response
    try {
      res = await fetch(url, { method: 'POST', body: form })
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
  updateGroup: (groupId: number, data: { name?: string; description?: string; avatar?: string }) =>
    req<import('./types').Group>(`/api/groups/${groupId}`, {
      method: 'PUT', body: body(data),
    }),
  deleteGroup: (groupId: number) => req<{ ok: boolean }>(`/api/groups/${groupId}`, { method: 'DELETE' }),

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

  // Group-scoped posts
  getGroupPosts: (groupId: number, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return req<{ posts: import('./types').Post[]; total: number }>(`/api/groups/${groupId}/posts${qs}`)
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
    req<import('./types').Post>(`/api/groups/${groupId}/posts/${postId}/publish`, { method: 'POST' }),

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
}
