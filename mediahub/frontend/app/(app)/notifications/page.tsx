'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { api } from '@/lib/api'
import StateWrapper from '@/components/StateWrapper'
import type { Notification } from '@/lib/types'

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
const TBGCOL: Record<string, string> = {
  success: 'var(--green-bg)',
  info:    'var(--blue-dim)',
  warning: 'var(--yellow-bg)',
  error:   'var(--red-bg)',
}

function fmtTime(s: string) {
  const d = new Date(s)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60)   return 'только что'
  if (diff < 3600) return `${Math.floor(diff / 60)} мин. назад`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч. назад`
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function NotificationsPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const [notifs, setNotifs] = useState<Notification[] | null>(null)

  function load() {
    api.getNotifications().then(data => setNotifs(data.items)).catch(console.error)
  }

  useEffect(() => {
    if (!user?.id) return
    load()
    const iv = setInterval(load, 30_000)
    return () => clearInterval(iv)
  }, [user?.id])

  async function markRead(id: number) {
    try { await api.markRead(id); load() }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  async function markAllRead() {
    const unread = (notifs ?? []).filter(n => !n.is_read)
    try {
      await Promise.all(unread.map(n => api.markRead(n.id)))
      load()
      showToast('Все отмечены как прочитанные', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  const unread = (notifs ?? []).filter(n => !n.is_read).length

  return (
    <div className="content">
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="card-title">Уведомления</span>
            {unread > 0 && (
              <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 8px', borderRadius: 'var(--r-full)', background: 'var(--red)', color: '#fff' }}>
                {unread}
              </span>
            )}
          </div>
          {unread > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={markAllRead} style={{ fontSize: 11.5 }}>
              Прочитать все
            </button>
          )}
        </div>

        <StateWrapper
          loading={notifs === null}
          empty={notifs !== null && notifs.length === 0}
          emptyText="Нет уведомлений"
          emptyFallback={
            <div style={{ padding: '52px 24px' }}>
              <div className="empty-state">
                <div className="empty-state-icon">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="2" x2="12" y2="4"/>
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                  </svg>
                </div>
                <div className="empty-state-title">Нет уведомлений</div>
                <div className="empty-state-sub">Здесь появятся уведомления о публикациях и событиях</div>
              </div>
            </div>
          }
          skeleton={[0,1,2,3].map(i => (
            <div key={i} style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 13, alignItems: 'center' }}>
              <div className="skeleton" style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0 }}/>
              <div style={{ flex: 1 }}>
                <div className="skeleton skeleton-text" style={{ width: '75%', marginBottom: 8 }}/>
                <div className="skeleton skeleton-text" style={{ width: '40%' }}/>
              </div>
            </div>
          ))}
        >
          {notifs?.map((n, i) => (
          <div
            key={n.id}
            className={`notif-item anim-in${!n.is_read ? ' unread' : ''}`}
            style={{ animationDelay: `${i * 30}ms`, cursor: !n.is_read ? 'pointer' : 'default' }}
            onClick={() => !n.is_read && markRead(n.id)}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 8, flexShrink: 0,
              background: n.is_read ? 'var(--surface-2)' : (TBGCOL[n.type] ?? 'var(--accent-light)'),
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: n.is_read ? 'var(--text-3)' : (TCOL[n.type] ?? 'var(--accent)'),
              transition: 'background var(--dur-base) var(--ease-out)',
            }}>
              {TICO[n.type] ?? TICO.info}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: n.is_read ? 400 : 600, lineHeight: 1.5 }}>
                {n.message}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                {fmtTime(n.created_at)}
              </div>
            </div>
            {!n.is_read && (
              <button
                className="btn btn-ghost btn-sm"
                style={{ fontSize: 11, flexShrink: 0, whiteSpace: 'nowrap' }}
                onClick={e => { e.stopPropagation(); markRead(n.id) }}
              >
                Прочитано
              </button>
            )}
            {!n.is_read && (
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: TCOL[n.type] ?? 'var(--accent)', flexShrink: 0 }} />
            )}
          </div>
        ))}
        </StateWrapper>
      </div>
    </div>
  )
}
