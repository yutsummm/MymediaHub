'use client'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useGroup } from '@/contexts/GroupContext'
import type { Post } from '@/lib/types'

const fmtN = (n: number) => n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + 'M' : n >= 1000 ? Math.round(n / 1000) + 'K' : String(n)
const fmtDt = (s: string | null) => {
  if (!s) return '—'
  const d = new Date(s)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' }) + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}
const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

const SL: Record<string, string> = { draft: 'Черновик', scheduled: 'Запланирован', published: 'Опубликован' }
const SC: Record<string, string> = { draft: 's-draft', scheduled: 's-scheduled', published: 's-published' }

const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const IcoEdit  = <svg {...S}><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
const IcoSend  = <svg {...S}><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
const IcoTrash = <svg {...S}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
const IcoSpin  = <svg {...S} style={{ animation: 'spin 0.7s linear infinite' }}><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>
const IcoSearch = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
const IcoCal   = <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>

const STATUSES = [
  { v: '',          l: 'Все' },
  { v: 'published', l: 'Опубликованы' },
  { v: 'scheduled', l: 'Запланированы' },
  { v: 'draft',     l: 'Черновики' },
]

function SkeletonRow() {
  return (
    <tr>
      <td><div className="skeleton skeleton-text" style={{ width: '70%', marginBottom: 6 }}/><div className="skeleton skeleton-text" style={{ width: '40%' }}/></td>
      <td><div className="skeleton" style={{ width: 80, height: 20, borderRadius: 20 }}/></td>
      <td><div className="skeleton" style={{ width: 32, height: 18, borderRadius: 20 }}/></td>
      <td><div className="skeleton skeleton-text" style={{ width: 60 }}/></td>
      <td><div className="skeleton skeleton-text" style={{ width: 80 }}/></td>
      <td><div className="skeleton skeleton-text" style={{ width: 40 }}/></td>
      <td><div style={{ display: 'flex', gap: 6 }}><div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }}/><div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }}/></div></td>
    </tr>
  )
}

const iconBtn: React.CSSProperties = {
  width: 28, height: 28, padding: 0,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 6, border: '1px solid var(--border)',
  background: 'transparent', cursor: 'pointer',
  color: 'var(--text-3)',
  transition: 'background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast)',
}

export default function PostsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user } = useAuth()
  const { showToast } = useToast()
  const { currentGroup } = useGroup()
  const [posts, setPosts] = useState<Post[] | null>(null)
  const [search, setSearch] = useState('')
  const [stFilter, setStFilter] = useState('')
  const [dateFilter, setDateFilter] = useState(searchParams.get('date') ?? '')
  const [pub, setPub] = useState<number | null>(null)

  function load() {
    const params: Record<string, string> = {}
    if (stFilter) params.status = stFilter
    setPosts(null)
    if (currentGroup) {
      api.getGroupPosts(currentGroup.id, params).then(d => setPosts(d.posts)).catch(console.error)
    } else {
      api.getPosts(params).then(d => setPosts(d.posts)).catch(console.error)
    }
  }
  useEffect(load, [stFilter, currentGroup])

  const filtered = (posts ?? []).filter(p => {
    if (search && !p.title.toLowerCase().includes(search.toLowerCase())) return false
    if (dateFilter) {
      const dt = (p.scheduled_at ?? p.published_at ?? p.created_at ?? '').slice(0, 10)
      if (dt !== dateFilter) return false
    }
    return true
  })

  const canEdit = user?.role !== 'volunteer'

  async function handleDelete(p: Post) {
    if (!confirm(`Удалить «${p.title}»?`)) return
    try {
      if (currentGroup) await api.deleteGroupPost(currentGroup.id, p.id)
      else await api.deletePost(p.id)
      showToast('Пост удалён', 'success'); load()
    }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  async function handlePublish(p: Post) {
    setPub(p.id)
    try {
      const result = currentGroup
        ? await api.publishGroupPost(currentGroup.id, p.id)
        : await api.publishPost(p.id)
      const r = result as any
      const errs: string[] = []
      const okParts: string[] = []
      if (r.vk_error) errs.push(`VK: ${r.vk_error}`)
      else if (r.vk_post_id) okParts.push(`VK (id: ${r.vk_post_id})`)
      if (r.photo_errors?.length) errs.push(`VK медиа: ${r.photo_errors[0]}`)
      if (r.tg_error) errs.push(`Telegram: ${r.tg_error}`)
      else if (r.tg_message_ids?.length) okParts.push(`Telegram (${r.tg_message_ids.length} сообщ.)`)
      if (errs.length) {
        showToast(okParts.length ? 'Опубликован частично' : 'Ошибка публикации', 'error', [...okParts.map(s => '+ ' + s), ...errs.map(s => '- ' + s)].join('\n'))
      } else if (okParts.length) {
        showToast('Пост опубликован', 'success', okParts.join('\n'))
      } else {
        showToast('Пост опубликован', 'success')
      }
      load()
    }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setPub(null) }
  }

  return (
    <div className="content">
      {/* Filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        {/* Status segment */}
        <div className="period-seg">
          {STATUSES.map(s => (
            <button
              key={s.v}
              className={`period-seg-btn${stFilter === s.v ? ' active' : ''}`}
              onClick={() => setStFilter(s.v)}
            >
              {s.l}
            </button>
          ))}
        </div>

        {/* Search */}
        <div style={{ position: 'relative', flex: 1, minWidth: 180, maxWidth: 300 }}>
          <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', pointerEvents: 'none', display: 'flex' }}>
            {IcoSearch}
          </span>
          <input
            className="srch"
            placeholder="Поиск по заголовку..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ paddingLeft: 34, width: '100%' }}
          />
          {search && (
            <button onClick={() => setSearch('')} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 16, lineHeight: 1 }}>×</button>
          )}
        </div>

        {/* Date chip */}
        {dateFilter && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 11px', background: 'var(--accent-light)', border: '1px solid var(--accent)', borderRadius: 'var(--r-full)', fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
            {IcoCal}
            {new Date(dateFilter + 'T00:00').toLocaleDateString('ru-RU', { day: '2-digit', month: 'long' })}
            <span style={{ cursor: 'pointer', opacity: 0.6, fontSize: 15, lineHeight: 1 }} onClick={() => setDateFilter('')}>×</span>
          </div>
        )}

        <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 'auto', fontWeight: 500 }}>
          {posts === null ? '...' : `${filtered.length} из ${posts.length}`}
        </span>

        {canEdit && (
          <button className="btn btn-primary" onClick={() => router.push('/posts/new')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Создать пост
          </button>
        )}
      </div>

      <div className="card">
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Заголовок</th>
                <th>Статус</th>
                <th>Платформы</th>
                <th>Теги</th>
                <th>Дата</th>
                <th>Охват</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {posts === null ? (
                [0,1,2,3,4].map(i => <SkeletonRow key={i} />)
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-state" style={{ padding: '48px 24px' }}>
                      <div className="empty-state-icon">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                          <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
                        </svg>
                      </div>
                      <div className="empty-state-title">{search || dateFilter ? 'Ничего не найдено' : 'Постов нет'}</div>
                      <div className="empty-state-sub">
                        {search || dateFilter ? 'Попробуйте изменить фильтры' : 'Создайте первый пост чтобы начать работу'}
                      </div>
                      {(search || dateFilter) && (
                        <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={() => { setSearch(''); setDateFilter(''); setStFilter('') }}>
                          Сбросить фильтры
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : filtered.map((p, i) => (
                <tr
                  key={p.id}
                  className="anim-in"
                  style={{ animationDelay: `${i * 30}ms`, cursor: canEdit ? 'pointer' : 'default' }}
                  onClick={() => canEdit && router.push(`/posts/${p.id}/edit`)}
                >
                  <td onClick={e => e.stopPropagation()}>
                    <div className="trunc" style={{ fontWeight: 600, fontSize: 13, maxWidth: 260, cursor: canEdit ? 'pointer' : 'default' }}
                      onClick={() => canEdit && router.push(`/posts/${p.id}/edit`)}
                    >{p.title}</div>
                    {p.author_name && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{p.author_name}</div>}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <span className={`sbadge ${SC[p.status]}`}>{SL[p.status]}</span>
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    {(p.platforms || []).length === 0 ? (
                      <span style={{ color: 'var(--text-3)' }}>—</span>
                    ) : (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {(p.platforms || []).map(pl => (
                          <span key={pl} className="pchip">
                            {pl === 'vk' ? 'ВК' : pl === 'telegram' ? 'TG' : pl.toUpperCase()}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', maxWidth: 160 }}>
                      {(p.tags || []).slice(0, 3).map(t => <span key={t} className="tag">{t}</span>)}
                      {(p.tags || []).length > 3 && <span className="tag">+{(p.tags || []).length - 3}</span>}
                      {(p.tags || []).length === 0 && <span style={{ color: 'var(--text-3)' }}>—</span>}
                    </div>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-2)', whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                    {p.status === 'published' ? fmtDt(p.published_at) : p.status === 'scheduled' ? fmtDt(p.scheduled_at) : fmtDate(p.created_at)}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-3)', whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                    {p.status === 'published' ? `${fmtN(p.views)} · ${p.reactions}` : '—'}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: 5 }}>
                      {canEdit && (
                        <button
                          style={{ ...iconBtn }}
                          onClick={() => router.push(`/posts/${p.id}/edit`)}
                          title="Редактировать"
                          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-h)'; (e.currentTarget as HTMLElement).style.color = 'var(--text)'; }}
                          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = 'var(--text-3)'; }}
                        >
                          {IcoEdit}
                        </button>
                      )}
                      {canEdit && (p.status === 'draft' || p.status === 'scheduled') && (
                        <button
                          style={{ ...iconBtn }}
                          onClick={() => handlePublish(p)}
                          disabled={pub === p.id}
                          title="Опубликовать"
                          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--green-bg)'; (e.currentTarget as HTMLElement).style.color = 'var(--green)'; (e.currentTarget as HTMLElement).style.borderColor = 'transparent'; }}
                          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = 'var(--text-3)'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
                        >
                          {pub === p.id ? IcoSpin : IcoSend}
                        </button>
                      )}
                      {user?.role === 'admin' && (
                        <button
                          style={{ ...iconBtn }}
                          onClick={() => handleDelete(p)}
                          title="Удалить"
                          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--red-bg)'; (e.currentTarget as HTMLElement).style.color = 'var(--red)'; (e.currentTarget as HTMLElement).style.borderColor = 'transparent'; }}
                          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = 'var(--text-3)'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
                        >
                          {IcoTrash}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
