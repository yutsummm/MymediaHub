'use client'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import type { Post } from '@/lib/types'

const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)
const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const fmtDt = (s: string | null) => {
  if (!s) return '—'
  const d = new Date(s)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' }) + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

const SL: Record<string, string> = { draft: 'Черновик', scheduled: 'Запланирован', published: 'Опубликован' }
const SC: Record<string, string> = { draft: 's-draft', scheduled: 's-scheduled', published: 's-published' }

/* ── SVG props ── */
const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const IcoEdit    = <svg {...S}><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
const IcoSend    = <svg {...S}><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
const IcoTrash   = <svg {...S}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>

export default function PostsPage() {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const { user }     = useAuth()
  const { showToast } = useToast()
  const [posts, setPosts]       = useState<Post[]>([])
  const [search, setSearch]     = useState('')
  const [stFilter, setStFilter] = useState('')
  const [dateFilter, setDateFilter] = useState(searchParams.get('date') ?? '')
  const [pub, setPub] = useState<number | null>(null)

  function load() {
    const params: Record<string, string> = {}
    if (stFilter) params.status = stFilter
    api.getPosts(params).then(d => setPosts(d.posts)).catch(console.error)
  }
  useEffect(load, [stFilter])

  const filtered = posts.filter(p => {
    if (search && !p.title.toLowerCase().includes(search.toLowerCase())) return false
    if (dateFilter) {
      const dt = (p.scheduled_at ?? p.published_at ?? p.created_at ?? '').slice(0, 10)
      if (dt !== dateFilter) return false
    }
    return true
  })
  const canEdit = user?.role !== 'observer'

  async function handleDelete(p: Post) {
    if (!confirm(`Удалить «${p.title}»?`)) return
    try { await api.deletePost(p.id); showToast('Пост удалён', 'success'); load() }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  async function handlePublish(p: Post) {
    setPub(p.id)
    try {
      const result = await api.publishPost(p.id)
      const r = result as any
      const errs: string[] = []
      const okParts: string[] = []
      if (r.vk_error) errs.push(`VK: ${r.vk_error}`)
      else if (r.vk_post_id) okParts.push(`VK (id: ${r.vk_post_id})`)
      if (r.vk_photo_errors?.length) errs.push(`VK медиа: ${r.vk_photo_errors[0]}`)
      if (r.tg_error) errs.push(`Telegram: ${r.tg_error}`)
      else if (r.tg_message_ids?.length) okParts.push(`Telegram (${r.tg_message_ids.length} сообщ.)`)
      if (errs.length) {
        showToast(
          okParts.length ? 'Опубликован частично' : 'Ошибка публикации',
          'error',
          [...okParts.map(s => '+ ' + s), ...errs.map(s => '- ' + s)].join('\n'),
        )
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
      <div className="filters-bar">
        <input className="srch" placeholder="Поиск..." value={search} onChange={e => setSearch(e.target.value)} />
        <select className="fsel" value={stFilter} onChange={e => setStFilter(e.target.value)}>
          <option value="">Все статусы</option>
          <option value="published">Опубликованы</option>
          <option value="scheduled">Запланированы</option>
          <option value="draft">Черновики</option>
        </select>
        {dateFilter && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px', background: 'var(--accent-light)', border: '1px solid var(--accent)', borderRadius: 'var(--r-md)', fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
            {new Date(dateFilter + 'T00:00').toLocaleDateString('ru-RU', { day: '2-digit', month: 'long' })}
            <span style={{ cursor: 'pointer', opacity: 0.7 }} onClick={() => setDateFilter('')}>×</span>
          </div>
        )}
        <span className="ts tg" style={{ marginLeft: 'auto' }}>{filtered.length} постов</span>
        {canEdit && (
          <button className="btn btn-primary" onClick={() => router.push('/posts/new')} style={{ gap: 6 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Создать пост
          </button>
        )}
      </div>

      <div className="card">
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Заголовок</th><th>Статус</th><th>Платформы</th><th>Теги</th><th>Дата</th><th>Охват</th><th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>Постов нет</td></tr>
              ) : filtered.map(p => (
                <tr key={p.id}>
                  <td>
                    <div className="trunc" style={{ fontWeight: 600, fontSize: 13, maxWidth: 260, color: 'var(--text)' }}>{p.title}</div>
                    {p.author_name && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{p.author_name}</div>}
                  </td>
                  <td><span className={`sbadge ${SC[p.status]}`}>{SL[p.status]}</span></td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(p.platforms || []).map(pl => (
                        <span key={pl} className="pchip">
                          {pl === 'vk' ? 'ВК' : pl === 'telegram' ? 'TG' : pl.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(p.tags || []).map(t => <span key={t} className="tag">{t}</span>)}
                    </div>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {p.status === 'published' ? fmtDt(p.published_at) : p.status === 'scheduled' ? fmtDt(p.scheduled_at) : fmtDate(p.created_at)}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {p.status === 'published' ? `${fmtN(p.views)} · ${p.reactions}` : '—'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {canEdit && (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => router.push(`/posts/${p.id}/edit`)}
                          title="Редактировать"
                        >
                          {IcoEdit}
                        </button>
                      )}
                      {canEdit && (p.status === 'draft' || p.status === 'scheduled') && (
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => handlePublish(p)}
                          disabled={pub === p.id}
                          title="Опубликовать"
                        >
                          {pub === p.id
                            ? <svg {...S}><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>
                            : IcoSend
                          }
                        </button>
                      )}
                      {user?.role === 'admin' && (
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDelete(p)}
                          title="Удалить"
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
