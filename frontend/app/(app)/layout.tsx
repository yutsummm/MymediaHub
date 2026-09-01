'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import Sidebar from '@/components/Sidebar'
import Breadcrumbs from '@/components/Breadcrumbs'
import GlobalSearch from '@/components/GlobalSearch'
import { api } from '@/lib/api'
import CreateGroupModal from '@/components/CreateGroupModal'

const TITLES: Record<string, string> = {
  '/dashboard':                  'Дашборд',
  '/calendar':                   'Календарь контента',
  '/youth-centers':              'Молодёжные центры рядом',
  '/posts':                      'Посты',
  '/posts/new':                  'Создать пост',
  '/comments':                   'Обращения',
  '/analytics':                  'Аналитика',
  '/settings':                   'Настройки',
  '/notifications':              'Уведомления',
  '/volunteer-media':            'Медиа волонтёров',
  '/volunteer-media/my':         'Мои загрузки',
  '/volunteer-media/upload':     'Загрузить медиа',
  '/help':                       'Справка',
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const { groups, currentGroup, loading: groupsLoading } = useGroup()
  const router = useRouter()
  const pathname = usePathname()
  const [unread, setUnread] = useState(0)
  const [pendingComments, setPendingComments] = useState(0)
  const [navOpen, setNavOpen] = useState(false)
  const [groupModalDismissed, setGroupModalDismissed] = useState(false)

  useEffect(() => { setNavOpen(false) }, [pathname])

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [user, loading, router])

  useEffect(() => {
    if (user) {
      api.getNotifications()
        .then(ns => setUnread(ns.items.filter(n => !n.is_read).length))
        .catch(() => {})
    }
  }, [user, pathname])

  // Обращения ждут ответа в срок, поэтому их число видно в меню всегда, а не
  // только на самой странице. Наблюдателям очередь недоступна — тихо глотаем
  // отказ, чтобы не показывать им ошибку на каждой странице.
  useEffect(() => {
    if (!user || !currentGroup) { setPendingComments(0); return }
    api.getCommentsSummary(currentGroup.id)
      .then(s => setPendingComments(s.pending))
      .catch(() => setPendingComments(0))
  }, [user, currentGroup, pathname])

  // Хук обязан вызываться до раннего return — иначе количество хуков между
  // рендерами меняется и React падает.
  const closeNav = useCallback(() => setNavOpen(false), [])

  if (loading || groupsLoading || !user) return null

  const title = TITLES[pathname] ?? (pathname.includes('/edit') ? 'Редактировать пост' : pathname)
  const today = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div style={{ display: 'flex', width: '100%' }}>
      <div className="top-stripe" />
      <Sidebar unread={unread} pendingComments={pendingComments} open={navOpen} onClose={closeNav} />

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
            <div className="topbar-breadcrumbs">
              <Breadcrumbs />
              <span className="topbar-title">{title}</span>
            </div>
          </div>
          <div className="topbar-actions">
            <GlobalSearch />
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
