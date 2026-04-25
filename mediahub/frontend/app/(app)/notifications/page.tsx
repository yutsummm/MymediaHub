'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import type { Notification } from '@/lib/types'

const TICO: Record<string, string> = { success: '✓', info: 'i', warning: '!', error: '×' }
const TCOL: Record<string, string> = { success: 'var(--green)', info: 'var(--blue)', warning: 'var(--yellow)', error: 'var(--red)' }

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
          <span className="card-title">Уведомления</span>
          {unread > 0 && (
            <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500 }}>
              {unread} непрочитанных
            </span>
          )}
        </div>
        {notifs.length === 0 ? (
          <div className="empty">
            <div className="empty-ico">◉</div>
            <div>Нет уведомлений</div>
          </div>
        ) : notifs.map(n => (
          <div key={n.id} className={`notif-item${!n.is_read ? ' unread' : ''}`}>
            <div style={{
              width: 22, height: 22, borderRadius: 6, flexShrink: 0,
              background: n.is_read ? 'var(--surface-2)' : (TCOL[n.type] ? TCOL[n.type].replace('var(', 'rgba(').replace(')', ',0.15)') : 'var(--accent-light)'),
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 800, color: TCOL[n.type] ?? 'var(--text-3)',
            }}>
              {TICO[n.type] ?? 'i'}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: n.is_read ? 400 : 500 }}>{n.message}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{n.created_at}</div>
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
