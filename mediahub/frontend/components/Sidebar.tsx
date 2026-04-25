'use client'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

const NAV = [
  { href: '/dashboard',      icon: '📊', label: 'Дашборд' },
  { href: '/calendar',       icon: '📅', label: 'Календарь' },
  { href: '/posts',          icon: '📝', label: 'Посты' },
  { href: '/posts/new',      icon: '✏️',  label: 'Создать пост' },
  { href: '/analytics',      icon: '📈', label: 'Аналитика' },
  { href: '/notifications',  icon: '🔔', label: 'Уведомления' },
  { href: '/settings',       icon: '⚙️',  label: 'Настройки' },
]

const ROLE_CLASS: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', observer: 'r-observer' }
const ROLE_LABEL: Record<string, string> = { admin: 'Администратор', editor: 'Редактор', observer: 'Наблюдатель' }

export default function Sidebar({ unread = 0 }: { unread?: number }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()

  function handleLogout() {
    logout()
    router.push('/login')
  }

  return (
    <div className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">📡</div>
        <div>
          <div className="logo-text">MediaHub</div>
          <div className="logo-sub">Молодёжные центры КК</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section">Навигация</div>
        {NAV.map(item => (
          <div
            key={item.href}
            className={`nav-item${pathname === item.href ? ' active' : ''}`}
            onClick={() => router.push(item.href)}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
            {item.href === '/notifications' && unread > 0 && (
              <span className="nav-badge">{unread}</span>
            )}
          </div>
        ))}
      </nav>

      {user && (
        <div className="sidebar-user">
          <div className="avatar">{user.avatar || user.name[0]}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.name}
            </div>
            <span className={`user-role-lbl ${ROLE_CLASS[user.role] ?? ''}`}>{ROLE_LABEL[user.role]}</span>
          </div>
          <button onClick={handleLogout} className="btn btn-ghost btn-sm" style={{ color: 'var(--gray-400)', padding: '4px 8px' }} title="Выйти">
            ↩
          </button>
        </div>
      )}
    </div>
  )
}
