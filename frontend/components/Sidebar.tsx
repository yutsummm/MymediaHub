'use client'
import { useEffect, useState, memo } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import Logo from '@/components/Logo'

type Theme = 'dark' | 'light' | 'system'

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
  users: (
    <svg {...S}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
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

// Роли в проекте двух видов, и раньше меню их путало: пункт про волонтёрские
// загрузки показывался по ГЛОБАЛЬНОЙ роли, хотя загрузки живут внутри группы.
//   groupRoles  — роль в текущей группе (group_members.role): что можно делать с контентом
//   globalRoles — роль в системе (users.role): администрирование, и только оно
type NavItem = {
  href: string
  icon: string
  label: string
  groupRoles?: string[]
  globalRoles?: string[]
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Основное',
    items: [
      { href: '/dashboard', icon: 'dashboard',     label: 'Дашборд' },
      { href: '/calendar',  icon: 'calendar',      label: 'Календарь' },
      { href: '/youth-centers', icon: 'centers',   label: 'Центры рядом' },
      { href: '/posts',     icon: 'posts',         label: 'Посты' },
      { href: '/posts/new', icon: 'newPost',       label: 'Создать пост', groupRoles: ['admin', 'editor'] },
    ],
  },
  {
    label: 'Медиа',
    items: [
      { href: '/volunteer-media',   icon: 'volunteerMedia', label: 'Медиа волонтёров', groupRoles: ['admin', 'editor'] },
      { href: '/volunteer-media/upload', icon: 'myUploads', label: 'Загрузить медиа',  groupRoles: ['volunteer'] },
      { href: '/volunteer-media/my',     icon: 'myUploads', label: 'Мои загрузки',     groupRoles: ['volunteer'] },
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
      { href: '/users',    icon: 'users',    label: 'Пользователи', globalRoles: ['admin'] },
      { href: '/settings', icon: 'settings', label: 'Настройки' },
    ],
  },
]

const ROLE_CLASS: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', volunteer: 'r-volunteer' }
const ROLE_LABEL: Record<string, string> = { admin: 'Администратор', editor: 'Редактор', volunteer: 'Волонтёр' }
const GLOBAL_ROLE_LABEL: Record<string, string> = { admin: 'Администратор системы', member: 'Участник' }
// Короткие подписи для чипов в сайдбаре: полные названия туда не помещаются.
const ROLE_SHORT: Record<string, string> = { admin: 'админ группы', editor: 'редактор', volunteer: 'волонтёр' }

function Sidebar({
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
    const stored = localStorage.getItem('mediahub-theme') as Theme | null
    setTheme(stored || 'dark')
  }, [])

  // Listen for OS theme changes when in system mode
  useEffect(() => {
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const handler = (e: MediaQueryListEvent) => {
      document.documentElement.setAttribute('data-theme', e.matches ? 'light' : 'dark')
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  function applyTheme(t: Theme) {
    if (t === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: light)')
      document.documentElement.setAttribute('data-theme', mq.matches ? 'light' : 'dark')
    } else {
      document.documentElement.setAttribute('data-theme', t)
    }
  }

  function toggleTheme() {
    const order: Theme[] = ['light', 'dark', 'system']
    const idx = order.indexOf(theme)
    const next = order[(idx + 1) % 3]
    setTheme(next)
    applyTheme(next)
    try { localStorage.setItem('mediahub-theme', next) } catch {}
  }

  const THEME_THUMB: Record<Theme, { icon: string; pos: string; title: string }> = {
    light:  { icon: '☀', pos: 'light', title: 'Светлая тема → Тёмная' },
    dark:   { icon: '☾', pos: 'dark', title: 'Тёмная тема → Системная' },
    system: { icon: '🖥', pos: 'system', title: 'Системная тема → Светлая' },
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
          {/* Сайдбар тёмный в обеих темах, поэтому знак белый безусловно.
              overflow — страховка на время подгрузки Comfortaa: запасной шрифт
              шире, и без неё знак на миг выталкивал бы кнопку закрытия. */}
          <Logo
            size={15}
            subtitle="молодёжных центров"
            style={{ flex: 1, minWidth: 0, overflow: 'hidden', color: '#fff' }}
          />
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
              style={{ background: 'none', border: 'none', fontFamily: 'inherit', color: 'rgba(255,255,255,0.35)', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 2px', fontWeight: 700 }}
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
            // Без выбранной группы человек работает в своём личном пространстве
            // (глобальные ручки) — там он сам себе редактор. Групповые пункты,
            // которым нужна настоящая группа, при этом остаются скрытыми.
            const groupRole = currentGroup?.role || (groups.length === 0 ? 'editor' : '')
            const globalRole = user?.role || ''
            const visible = group.items.filter(i =>
              (!i.groupRoles || i.groupRoles.includes(groupRole)) &&
              (!i.globalRoles || i.globalRoles.includes(globalRole))
            )
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
            </div>
            <div
              className="theme-toggle"
              data-theme-state={THEME_THUMB[theme].pos}
              role="switch"
              aria-checked={theme !== 'dark'}
              tabIndex={0}
              onClick={toggleTheme}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleTheme() } }}
              title={THEME_THUMB[theme].title}
            >
              <div className="theme-toggle-thumb">{THEME_THUMB[theme].icon}</div>
            </div>
            <button
              onClick={handleLogout}
              className="btn btn-ghost btn-sm"
              style={{ padding: '4px 8px', fontSize: 16, lineHeight: 1 }}
              title="Выйти"
            >
              ↩
            </button>

            {/* Обе роли показываем сознательно: групповая отвечает за работу с
                контентом, глобальная — за администрирование системы, и путать их
                нельзя. Но рядом с именем им доставалось 90 px при нужных 104,
                поэтому они занимают собственную строку во всю ширину панели. */}
            <div className="user-roles">
              {currentGroup && (
                <span className={`user-role-lbl ${ROLE_CLASS[currentGroup.role] ?? ''}`}
                  title={`${ROLE_LABEL[currentGroup.role] ?? currentGroup.role} в группе «${currentGroup.name}»`}>
                  {ROLE_SHORT[currentGroup.role] ?? currentGroup.role}
                </span>
              )}
              {user.role === 'admin' && (
                <span className="user-role-lbl r-admin" title={`${GLOBAL_ROLE_LABEL.admin} — роль в системе`}>
                  админ системы
                </span>
              )}
              {!currentGroup && user.role !== 'admin' && (
                <span className="user-role-lbl" title="Роль в системе">
                  {GLOBAL_ROLE_LABEL[user.role] ?? user.role}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}

export default memo(Sidebar)
