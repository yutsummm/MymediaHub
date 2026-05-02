'use client'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'

type Theme = 'dark' | 'light'

const NAV = [
  { href: '/dashboard',     icon: '◈', label: 'Дашборд' },
  { href: '/calendar',      icon: '◷', label: 'Календарь' },
  { href: '/posts',         icon: '≡',  label: 'Посты' },
  { href: '/posts/new',     icon: '+',  label: 'Создать пост' },
  { href: '/analytics',     icon: '↗', label: 'Аналитика' },
  { href: '/notifications', icon: '◉', label: 'Уведомления' },
  { href: '/settings',      icon: '◎', label: 'Настройки' },
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
          <div className="logo-mark-wrap" aria-label="Медиа-Хаб">
            <img src="/logo.png" alt="" className="logo-mark-img" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="logo-text">Медиа-Хаб</div>
            <div className="logo-sub">Молодёжные центры КК</div>
          </div>
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
          <div className="nav-section">Навигация</div>
          {NAV.map(item => (
            <div
              key={item.href}
              className={`nav-item${pathname === item.href ? ' active' : ''}`}
              onClick={() => go(item.href)}
            >
              <span className="nav-icon" style={{ fontStyle: 'normal', fontFamily: 'monospace' }}>
                {item.icon}
              </span>
              {item.label}
              {item.href === '/notifications' && unread > 0 && (
                <span className="nav-badge">{unread}</span>
              )}
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
