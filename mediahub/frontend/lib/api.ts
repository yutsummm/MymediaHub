// На проде используем относительные URL — Next.js rewrites проксирует /api/* на бэк
// (см. next.config.mjs / BACKEND_URL). Локально NEXT_PUBLIC_API_URL=http://localhost:8000.
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${BASE}${path}`
  let res: Response
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
      ...init,
    })
  } catch (e) {
    throw new Error(`Сеть недоступна (${url}): ${(e as Error).message}`)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let detail: string | undefined
    try { detail = JSON.parse(text)?.detail } catch {}
    throw new Error(detail ?? `${res.status} ${res.statusText} — ${url}`)
  }
  return res.json()
}

const body = (data: unknown) => JSON.stringify(data)

export const api = {
  login: (email: string) =>
    req<{ user: import('./types').User; token: string }>('/api/auth/login', {
      method: 'POST', body: body({ email, password: 'demo' }),
    }),

  getUsers: () => req<import('./types').User[]>('/api/users'),
  updateUserRole: (id: number, role: string) =>
    req<import('./types').User>(`/api/users/${id}/role`, { method: 'PUT', body: body({ role }) }),

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

  getAnalyticsSummary: () => req<import('./types').AnalyticsSummary>('/api/analytics/summary'),
  getTimeline: (period: string) =>
    req<import('./types').TimelinePoint[]>(`/api/analytics/timeline?period=${period}`),

  getNotifications: (user_id?: number) =>
    req<import('./types').Notification[]>(`/api/notifications${user_id ? `?user_id=${user_id}` : ''}`),
  markRead: (id: number) => req<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: 'PUT' }),

  getVkSettings: () => req<import('./types').VkSettings>('/api/settings/vk'),
  saveVkSettings: (group_id: string, access_token: string) =>
    req<import('./types').VkSettings>('/api/settings/vk', {
      method: 'POST', body: body({ group_id, access_token }),
    }),
  deleteVkSettings: () => req<{ connected: boolean }>('/api/settings/vk', { method: 'DELETE' }),
}
