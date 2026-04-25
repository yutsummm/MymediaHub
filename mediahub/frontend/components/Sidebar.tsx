'use client'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

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

export default function Sidebar({ unread = 0 }: { unread?: number }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()
  const [theme, setTheme] = useState<Theme>('dark')

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

  return (
    <div className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-mark-wrap" aria-label="Медиа-Хаб">
          <img src="/logo.png" alt="" className="logo-mark-img" />
        </div>
        <div>
          <div className="logo-text">Медиа-Хаб</div>
          <div className="logo-sub">Молодёжные центры КК</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="nav-section">Навигация</div>
        {NAV.map(item => (
          <div
            key={item.href}
            className={`nav-item${pathname === item.href ? ' active' : ''}`}
            onClick={() => router.push(item.href)}
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
            <span className={`user-role-lbl ${ROLE_CLASS[user.role] ?? ''}`}>
              {ROLE_LABEL[user.role]}
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
  )
}
