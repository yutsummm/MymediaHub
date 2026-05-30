'use client'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'

type Theme = 'dark' | 'light'

const S = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const NAV_ICONS: Record<string, React.ReactNode> = {
  /* Бенто-сетка — «обзор всего» */
  dashboard: (
    <svg {...S}>
      <rect x="3" y="3" width="8" height="9" rx="1.5"/>
      <rect x="13" y="3" width="8" height="5" rx="1.5"/>
      <rect x="13" y="10" width="8" height="11" rx="1.5"/>
      <rect x="3" y="14" width="8" height="7" rx="1.5"/>
    </svg>
  ),
  /* Календарь с точками событий */
  calendar: (
    <svg {...S}>
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <line x1="16" y1="2" x2="16" y2="6"/>
      <line x1="8" y1="2" x2="8" y2="6"/>
      <line x1="3" y1="10" x2="21" y2="10"/>
      <circle cx="8"  cy="15" r="1" fill="currentColor" stroke="none"/>
      <circle cx="12" cy="15" r="1" fill="currentColor" stroke="none"/>
      <circle cx="16" cy="15" r="1" fill="currentColor" stroke="none"/>
    </svg>
  ),
  centers: (
    <svg {...S}>
      <path d="M12 21s7-4.35 7-11a7 7 0 0 0-14 0c0 6.65 7 11 7 11z"/>
      <circle cx="12" cy="10" r="2.5"/>
      <path d="M8.2 18.3h7.6"/>
    </svg>
  ),
  /* Документ с разными строками — «контент» */
  posts: (
    <svg {...S}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="13" y1="17" x2="8" y2="17"/>
    </svg>
  ),
  /* Редактировать в квадрате — «создать» */
  newPost: (
    <svg {...S}>
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  /* Пульс / активность — «живые данные» */
  analytics: (
    <svg {...S}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  ),
  /* Колокол со стержнем — «уведомления» */
  notifications: (
    <svg {...S}>
      <line x1="12" y1="2" x2="12" y2="4"/>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
      <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  /* Камера — «медиа от волонтёров» */
  volunteerMedia: (
    <svg {...S}>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </svg>
  ),
  /* Мои загрузки — облако со стрелкой вверх */
  myUploads: (
    <svg {...S}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <polyline points="12 12 12 18"/>
      <polyline points="9 15 12 12 15 15"/>
    </svg>
  ),
  /* Микшер со скруглёнными ручками — «управление» */
  settings: (
    <svg {...S}>
      <line x1="4" y1="21" x2="4" y2="14"/>
      <line x1="4" y1="10" x2="4" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="12"/>
      <line x1="12" y1="8" x2="12" y2="3"/>
      <line x1="20" y1="21" x2="20" y2="16"/>
      <line x1="20" y1="12" x2="20" y2="3"/>
      <circle cx="4"  cy="12" r="2"/>
      <circle cx="12" cy="10" r="2"/>
      <circle cx="20" cy="14" r="2"/>
    </svg>
  ),
}

type NavItem = { href: string; icon: string; label: string; roles?: string[] }

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Основное',
    items: [
      { href: '/dashboard', icon: 'dashboard',     label: 'Дашборд' },
      { href: '/calendar',  icon: 'calendar',      label: 'Календарь' },
      { href: '/youth-centers', icon: 'centers',   label: 'Центры рядом' },
      { href: '/posts',     icon: 'posts',         label: 'Посты' },
      { href: '/posts/new', icon: 'newPost',       label: 'Создать пост', roles: ['admin', 'editor'] },
    ],
  },
  {
    label: 'Медиа',
    items: [
      { href: '/volunteer-media',   icon: 'volunteerMedia', label: 'Медиа волонтёров', roles: ['admin', 'editor'] },
      { href: '/volunteer-media/upload', icon: 'myUploads', label: 'Загрузить медиа',  roles: ['volunteer'] },
      { href: '/volunteer-media/my',     icon: 'myUploads', label: 'Мои загрузки',     roles: ['volunteer'] },
    ],
  },
  {
    label: 'Аналитика',
    items: [
      { href: '/analytics',     icon: 'analytics',      label: 'Аналитика' },
      { href: '/notifications', icon: 'notifications',  label: 'Уведомления' },
    ],
  },
  {
    label: 'Управление',
    items: [
      { href: '/settings', icon: 'settings', label: 'Настройки' },
    ],
  },
]

const ROLE_CLASS: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', volunteer: 'r-volunteer' }
const ROLE_LABEL: Record<string, string> = { admin: 'Администратор', editor: 'Редактор', volunteer: 'Волонтёр' }

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

        {/* Groups — always visible */}
        <div style={{ padding: '4px 8px 0' }}>
          <div className="nav-group" style={{ paddingTop: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Группы</span>
            <button
              onClick={() => { router.push('/groups/new'); onClose?.() }}
              style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.35)', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 2px', fontWeight: 700 }}
              title="Создать группу"
            >+</button>
          </div>
          {groups.length === 0 ? (
            <div className="nav-item" style={{ cursor: 'default', opacity: 0.5, pointerEvents: 'none' }}>
              <span className="nav-icon" style={{ fontSize: 9, fontWeight: 700 }}>—</span>
              <span style={{ fontSize: 12, color: 'inherit' }}>Нет групп</span>
            </div>
          ) : (
            groups.map(g => (
              <button
                key={g.id}
                onClick={() => { switchGroup(g.id); onClose?.() }}
                className={`nav-item${currentGroup?.id === g.id ? ' active' : ''}`}
                style={{
                  width: '100%', textAlign: 'left', display: 'flex',
                  alignItems: 'center', gap: 10, marginBottom: 1,
                }}
              >
                <span className="nav-icon" style={{ fontSize: 9, fontWeight: 700 }}>{g.name[0].toUpperCase()}</span>
                <span style={{ flex: 1, minWidth: 0, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                  {g.name}
                </span>
              </button>
            ))
          )}
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav">
          {NAV_GROUPS.map(group => {
            const role = currentGroup?.role || user?.role || ''
            const visible = group.items.filter(i => !i.roles || i.roles.includes(role))
            if (visible.length === 0) return null
            return (
            <div key={group.label}>
              <div className="nav-group">{group.label}</div>
              {visible.map(item => (
                <div
                  key={item.href}
                  className={`nav-item${pathname === item.href ? ' active' : ''}`}
                  onClick={() => go(item.href)}
                >
                  <span className="nav-icon">
                    {NAV_ICONS[item.icon as keyof typeof NAV_ICONS]}
                  </span>
                  {item.label}
                  {item.href === '/notifications' && unread > 0 && (
                    <span className="nav-badge">{unread}</span>
                  )}
                </div>
              ))}
            </div>
          )
        })}
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
