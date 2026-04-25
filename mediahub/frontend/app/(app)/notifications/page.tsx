'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import type { Notification } from '@/lib/types'

const TICO: Record<string, string> = { success: '✅', info: 'ℹ️', warning: '⚠️', error: '❌' }

export default function NotificationsPage() {
  const { user } = useAuth()
  const [notifs, setNotifs] = useState<Notification[]>([])

  function load() {
    api.getNotifications(user?.id).then(setNotifs).catch(console.error)
  }
  useEffect(load, [user?.id])

  async function markRead(id: number) {
    await api.markRead(id)
    load()
  }

  const unread = notifs.filter(n => !n.is_read).length

  return (
    <div className="content">
      <div className="card">
        <div className="card-header">
          <span className="card-title">🔔 Уведомления</span>
          {unread > 0 && <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>{unread} непрочитанных</span>}
        </div>
        {notifs.length === 0 ? (
          <div className="empty"><div className="empty-ico">🔔</div>Нет уведомлений</div>
        ) : notifs.map(n => (
          <div key={n.id} className={`notif-item${!n.is_read ? ' unread' : ''}`}>
            <div className={`ndot${n.is_read ? ' read' : ''}`} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14 }}>{TICO[n.type] ?? 'ℹ️'} {n.message}</div>
              <div style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 4 }}>{n.created_at}</div>
            </div>
            {!n.is_read && (
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={() => markRead(n.id)}>
                Прочитано
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
