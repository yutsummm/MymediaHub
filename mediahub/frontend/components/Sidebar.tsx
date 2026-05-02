'use client'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'

type Theme = 'dark' | 'light'

const SI = { fill:'none' as const, stroke:'currentColor', strokeWidth:1.75, strokeLinecap:'round' as const, strokeLinejoin:'round' as const }

const NAV_ICONS: Record<string, React.ReactNode> = {
  '/dashboard':     <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>,
  '/calendar':      <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>,
  '/posts':         <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>,
  '/posts/new':     <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>,
  '/analytics':     <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>,
  '/notifications': <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
  '/settings':      <svg width="15" height="15" viewBox="0 0 24 24" {...SI}><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>,
}

const NAV_GROUPS = [
  {
    label: 'Основное',
    items: [
      { href: '/dashboard', label: 'Дашборд' },
      { href: '/calendar',  label: 'Календарь' },
      { href: '/posts',     label: 'Посты' },
      { href: '/posts/new', label: 'Создать пост' },
    ],
  },
  {
    label: 'Аналитика',
    items: [
      { href: '/analytics',     label: 'Аналитика' },
      { href: '/notifications', label: 'Уведомления' },
    ],
  },
  {
    label: 'Управление',
    items: [
      { href: '/settings', label: 'Настройки' },
    ],
  },
]

const ROLE_CLASS: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', observer: 'r-observer' }
const ROLE_LABEL: Record<string, string> = { admin: 'Администратор', editor: 'Редактор', observer: 'Наблюдатель' }

export default function Sidebar({
  unread = 0,
  open = false,
  onClose,
}: {
  unread?: number
  open?: boolean
  onClose?: () => void
}) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()
  const { groups, currentGroup, switchGroup } = useGroup()
  const [theme, setTheme] = useState<Theme>('dark')
  const [showGroups, setShowGroups] = useState(false)

  useEffect(() => {
    const initial = (document.documentElement.getAttribute('data-theme') as Theme) || 'dark'
    setTheme(initial)
  }, [])

  function toggleTheme() {
    const next: Theme = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    try { localStorage.setItem('mediahub-theme', next) } catch {}
  }

  function handleLogout() {
    logout()
    router.push('/login')
  }

  function go(href: string) {
    router.push(href)
    onClose?.()
  }

  return (
    <>
      <div
        className={`sidebar-backdrop${open ? ' show' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div className={`sidebar${open ? ' open' : ''}`}>
        {/* Logo */}
        <div className="sidebar-logo">
          <svg viewBox="0 0 212 46" xmlns="http://www.w3.org/2000/svg" style={{ display: 'block', flex: 1, minWidth: 0 }}>
            <rect x="0"  y="3"  width="7" height="36" rx="1.5" fill="white"/>
            <rect x="10" y="11" width="7" height="28" rx="1.5" fill="rgba(255,255,255,0.48)"/>
            <rect x="20" y="19" width="7" height="20" rx="1.5" fill="rgba(255,255,255,0.26)"/>
            <rect x="30" y="11" width="7" height="28" rx="1.5" fill="rgba(255,255,255,0.48)"/>
            <rect x="40" y="3"  width="7" height="36" rx="1.5" fill="white"/>
            <rect x="0" y="41" width="47" height="3" rx="1.5" fill={theme === 'light' ? '#5B9EFF' : 'rgba(255,255,255,0.28)'}/>
            <line x1="57" y1="4" x2="57" y2="40" stroke="rgba(255,255,255,0.10)" strokeWidth="1"/>
            <text x="66" y="19" fontFamily="'Inter','Arial',sans-serif" fontSize="10" fontWeight="700" fill="white" letterSpacing="0">МЕДИАПРОСТРАНСТВО</text>
            <text x="66" y="34" fontFamily="'Inter','Arial',sans-serif" fontSize="8.5" fontWeight="400" fill="rgba(255,255,255,0.36)" letterSpacing="0">молодёжных центров</text>
          </svg>
          <button
            type="button"
            className="sidebar-close"
            aria-label="Закрыть меню"
            onClick={onClose}
          >×</button>
        </div>

        {/* Groups Switcher */}
        {groups.length > 0 && (
          <div style={{ padding: '0 12px 16px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Группа
            </div>
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setShowGroups(!showGroups)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 'var(--r-md)',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-1)',
                  fontSize: 14,
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ minWidth: 0, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                  {currentGroup?.name || 'Выберите группу'}
                </span>
                <span style={{ fontSize: 10, flexShrink: 0 }}>▼</span>
              </button>
              {showGroups && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  marginTop: 4,
                  borderRadius: 'var(--r-md)',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-secondary)',
                  zIndex: 10,
                  maxHeight: 300,
                  overflowY: 'auto',
                }}>
                  {groups.map(g => (
                    <button
                      key={g.id}
                      onClick={() => {
                        switchGroup(g.id)
                        setShowGroups(false)
                        onClose?.()
                      }}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        border: 'none',
                        background: currentGroup?.id === g.id ? 'rgba(139,92,246,0.1)' : 'transparent',
                        color: currentGroup?.id === g.id ? 'var(--accent)' : 'var(--text-2)',
                        fontSize: 13,
                        fontWeight: currentGroup?.id === g.id ? 600 : 400,
                        cursor: 'pointer',
                        textAlign: 'left',
                        borderBottom: '1px solid var(--border)',
                      }}
                    >
                      {g.name}
                      {currentGroup?.id === g.id && <span style={{ marginLeft: 8 }}>✓</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => {
                router.push('/groups/new')
                onClose?.()
              }}
              style={{
                width: '100%',
                marginTop: 8,
                padding: '8px 12px',
                borderRadius: 'var(--r-md)',
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--accent)',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              + Новая группа
            </button>
          </div>
        )}

        {/* Navigation */}
        <nav className="sidebar-nav">
          {NAV_GROUPS.map(group => (
            <div key={group.label}>
              <div className="nav-group">{group.label}</div>
              {group.items.map(item => (
                <div
                  key={item.href}
                  className={`nav-item${pathname === item.href ? ' active' : ''}`}
                  onClick={() => go(item.href)}
                >
                  <span className="nav-icon">
                    {NAV_ICONS[item.href]}
                  </span>
                  {item.label}
                  {item.href === '/notifications' && unread > 0 && (
                    <span className="nav-badge">{unread}</span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </nav>

        {/* User profile */}
        {user && (
          <div className="sidebar-user">
            <div className="avatar">{user.name[0].toUpperCase()}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="user-name">{user.name}</div>
              <span className={`user-role-lbl ${ROLE_CLASS[currentGroup?.role || user.role] ?? ''}`}>
                {ROLE_LABEL[currentGroup?.role || user.role]}
              </span>
            </div>
            <div
              className="theme-toggle"
              role="switch"
              aria-checked={theme === 'light'}
              tabIndex={0}
              onClick={toggleTheme}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleTheme() } }}
              title={theme === 'light' ? 'Светлая тема — переключить на тёмную' : 'Тёмная тема — переключить на светлую'}
            >
              <div className="theme-toggle-thumb">{theme === 'light' ? '☀' : '☾'}</div>
            </div>
            <button
              onClick={handleLogout}
              className="btn btn-ghost btn-sm"
              style={{ padding: '4px 8px', fontSize: 16, lineHeight: 1 }}
              title="Выйти"
            >
              ↩
            </button>
          </div>
        )}
      </div>
    </>
  )
}
