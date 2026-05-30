'use client'
import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import Sidebar from '@/components/Sidebar'
import { api } from '@/lib/api'
import CreateGroupModal from '@/components/CreateGroupModal'

const TITLES: Record<string, string> = {
  '/dashboard':                  'Дашборд',
  '/calendar':                   'Календарь контента',
  '/youth-centers':              'Молодёжные центры рядом',
  '/posts':                      'Посты',
  '/posts/new':                  'Создать пост',
  '/analytics':                  'Аналитика',
  '/settings':                   'Настройки',
  '/notifications':              'Уведомления',
  '/volunteer-media':            'Медиа волонтёров',
  '/volunteer-media/my':         'Мои загрузки',
  '/volunteer-media/upload':     'Загрузить медиа',
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const { groups, currentGroup, switchGroup, loading: groupsLoading } = useGroup()
  const router = useRouter()
  const pathname = usePathname()
  const [unread, setUnread] = useState(0)
  const [navOpen, setNavOpen] = useState(false)
  const [groupModalDismissed, setGroupModalDismissed] = useState(false)
  const [showGroupPicker, setShowGroupPicker] = useState(false)

  useEffect(() => { setNavOpen(false) }, [pathname])

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

  if (loading || groupsLoading || !user) return null

  const title = TITLES[pathname] ?? (pathname.includes('/edit') ? 'Редактировать пост' : pathname)
  const today = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div style={{ display: 'flex', width: '100%' }}>
      <div className="top-stripe" />
      <Sidebar unread={unread} open={navOpen} onClose={() => setNavOpen(false)} />

      <div className="main-layout">
        {/* Topbar */}
        <div className="topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <button
              type="button"
              className="nav-burger"
              aria-label="Открыть меню"
              onClick={() => setNavOpen(true)}
            >
              <span /><span /><span />
            </button>
            <span className="topbar-title">{title}</span>
          </div>
          <div className="topbar-actions">
            {/* Group picker — always visible */}
            {groups.length > 0 && (
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setShowGroupPicker(!showGroupPicker)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 10px', borderRadius: 'var(--r-full)',
                    border: '1px solid var(--border)',
                    background: 'var(--surface)',
                    color: 'var(--text-2)',
                    fontSize: 12, fontWeight: 500, cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <span style={{
                    width: 14, height: 14, borderRadius: 4, flexShrink: 0,
                    background: 'var(--accent)', color: 'var(--btn-primary-fg)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 7, fontWeight: 700,
                  }}>
                    {currentGroup?.name?.[0]?.toUpperCase() || '?'}
                  </span>
                  {currentGroup?.name || 'Группа'}
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, opacity: 0.5 }}>
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                {showGroupPicker && (
                  <>
                    <div
                      style={{ position: 'fixed', inset: 0, zIndex: 99 }}
                      onClick={() => setShowGroupPicker(false)}
                    />
                    <div style={{
                      position: 'absolute', top: '100%', right: 0, marginTop: 4,
                      borderRadius: 'var(--r-md)', border: '1px solid var(--border)',
                      background: 'var(--surface)', zIndex: 100,
                      minWidth: 180, maxHeight: 240, overflowY: 'auto',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
                    }}>
                      {groups.map(g => (
                        <button
                          key={g.id}
                          onClick={() => { switchGroup(g.id); setShowGroupPicker(false) }}
                          style={{
                            width: '100%', padding: '9px 12px', border: 'none',
                            background: currentGroup?.id === g.id ? 'rgba(139,92,246,0.1)' : 'transparent',
                            color: currentGroup?.id === g.id ? 'var(--accent)' : 'var(--text-2)',
                            fontSize: 12.5, fontWeight: currentGroup?.id === g.id ? 600 : 400,
                            cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 8,
                            borderBottom: '1px solid var(--border)',
                          }}
                        >
                          <span style={{
                            width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                            background: currentGroup?.id === g.id ? 'var(--accent)' : 'var(--surface-2)',
                            color: currentGroup?.id === g.id ? 'var(--btn-primary-fg)' : 'var(--text-3)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 8, fontWeight: 700,
                          }}>
                            {g.name[0]?.toUpperCase()}
                          </span>
                          {g.name}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
            <span className="topbar-date" style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 500, letterSpacing: '0.02em' }}>
              {today}
            </span>
            {groups.length > 0 && groups[0]?.role !== 'volunteer' && (
              <button className="btn btn-primary btn-sm" onClick={() => router.push('/posts/new')}>
                Новый пост
                <span className="btn-icon" style={{ width: 20, height: 20, fontSize: 12 }}>+</span>
              </button>
            )}
          </div>
        </div>

        {children}
      </div>

      {!groupsLoading && groups.length === 0 && !groupModalDismissed && (
        <CreateGroupModal onClose={() => setGroupModalDismissed(true)} />
      )}
    </div>
  )
}
