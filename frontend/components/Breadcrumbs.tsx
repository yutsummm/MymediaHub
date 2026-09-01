'use client'
import { usePathname } from 'next/navigation'
import { useMemo } from 'react'

const LABELS: Record<string, string> = {
  dashboard: 'Дашборд',
  calendar: 'Календарь',
  'youth-centers': 'Молодёжные центры',
  posts: 'Посты',
  new: 'Создать',
  edit: 'Редактировать',
  analytics: 'Аналитика',
  settings: 'Настройки',
  notifications: 'Уведомления',
  'volunteer-media': 'Медиа волонтёров',
  upload: 'Загрузить',
  my: 'Мои загрузки',
  groups: 'Группы',
  help: 'Справка',
}

export default function Breadcrumbs({ classNames = '' }: { classNames?: string }) {
  const pathname = usePathname()

  const crumbs = useMemo(() => {
    const segments = pathname.split('/').filter(Boolean)
    if (segments.length <= 1) return null

    return segments.map((seg, i) => {
      const href = '/' + segments.slice(0, i + 1).join('/')
      const label = LABELS[seg] || decodeURIComponent(seg)
      return { href, label, current: i === segments.length - 1 }
    })
  }, [pathname])

  if (!crumbs || crumbs.length <= 1) return null

  return (
    <div className={`breadcrumbs ${classNames}`}>
      {crumbs.map((crumb, i) => (
        <span key={crumb.href} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {i > 0 && <span className="breadcrumbs-sep">/</span>}
          <span className={`breadcrumbs-item${crumb.current ? ' current' : ''}`}>
            {crumb.label}
          </span>
        </span>
      ))}
    </div>
  )
}
