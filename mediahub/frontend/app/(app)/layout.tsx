'use client'
import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import Sidebar from '@/components/Sidebar'
import { api } from '@/lib/api'

const TITLES: Record<string, string> = {
  '/dashboard':     '📊 Дашборд',
  '/calendar':      '📅 Календарь контента',
  '/posts':         '📝 Посты',
  '/posts/new':     '✏️ Создать пост',
  '/analytics':     '📈 Аналитика',
  '/settings':      '⚙️ Настройки',
  '/notifications': '🔔 Уведомления',
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [user, loading, router])

  useEffect(() => {
    if (user) {
      api.getNotifications(user.id)
        .then(ns => setUnread(ns.filter(n => !n.is_read).length))
        .catch(() => {})
    }
  }, [user, pathname])

  if (loading || !user) return null

  const title = TITLES[pathname] ?? (pathname.includes('/edit') ? '✏️ Редактировать пост' : pathname)
  const today = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div style={{ display: 'flex', width: '100%' }}>
      <Sidebar unread={unread} />
      <div className="main-layout">
        <div className="topbar">
          <span className="topbar-title">{title}</span>
          <div className="topbar-actions">
            <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>{today}</span>
            {user.role !== 'observer' && (
              <button className="btn btn-primary btn-sm" onClick={() => router.push('/posts/new')}>
                + Пост
              </button>
            )}
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}
