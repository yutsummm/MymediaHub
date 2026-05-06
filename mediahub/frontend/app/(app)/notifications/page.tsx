'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { api } from '@/lib/api'
import type { Notification } from '@/lib/types'

/* ── SVG icons ── */
const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const TICO: Record<string, React.ReactNode> = {
  success: <svg {...S}><polyline points="20 6 9 17 4 12"/></svg>,
  info:    <svg {...S}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
  warning: <svg {...S}><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  error:   <svg {...S}><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>,
}
const TCOL: Record<string, string> = {
  success: 'var(--green)',
  info:    'var(--blue)',
  warning: 'var(--yellow)',
  error:   'var(--red)',
}

export default function NotificationsPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const [notifs, setNotifs] = useState<Notification[]>([])

  function load() {
    api.getNotifications(user?.id).then(setNotifs).catch(console.error)
  }
  useEffect(load, [user?.id])

  async function markRead(id: number) {
    try { await api.markRead(id); load() }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
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
          <div className="empty-state" style={{ padding: '48px 24px' }}>
            <div className="empty-state-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.75" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="2" x2="12" y2="4"/>
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
              </svg>
            </div>
            <div className="empty-state-title">Нет уведомлений</div>
            <div className="empty-state-sub">Здесь появятся уведомления о публикациях и событиях</div>
          </div>
        ) : notifs.map((n, i) => (
          <div
            key={n.id}
            className={`notif-item${!n.is_read ? ' unread' : ''}`}
            style={{ animationDelay: `${i * 30}ms` }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: 8, flexShrink: 0,
              background: n.is_read
                ? 'var(--surface-2)'
                : `color-mix(in srgb, ${TCOL[n.type] ?? 'var(--accent)'} 15%, transparent)`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: n.is_read ? 'var(--text-3)' : (TCOL[n.type] ?? 'var(--accent)'),
              transition: 'background 0.2s var(--ease-out)',
            }}>
              {TICO[n.type] ?? TICO.info}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: n.is_read ? 400 : 600, lineHeight: 1.4 }}>
                {n.message}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>{n.created_at}</div>
            </div>
            {!n.is_read && (
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, flexShrink: 0 }} onClick={() => markRead(n.id)}>
                Прочитано
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
