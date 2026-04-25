'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
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
const DOT: Record<string, string> = { draft: '○', scheduled: '◑', published: '●' }
const PI: Record<string, string> = { vk: 'ВК', telegram: 'TG' }

export default function PostsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const { showToast } = useToast()
  const [posts, setPosts] = useState<Post[]>([])
  const [search, setSearch] = useState('')
  const [stFilter, setStFilter] = useState('')
  const [pub, setPub] = useState<number | null>(null)

  function load() {
    const params: Record<string, string> = {}
    if (stFilter) params.status = stFilter
    api.getPosts(params).then(d => setPosts(d.posts)).catch(console.error)
  }
  useEffect(load, [stFilter])

  const filtered = search ? posts.filter(p => p.title.toLowerCase().includes(search.toLowerCase())) : posts
  const canEdit = user?.role !== 'observer'

  async function handleDelete(p: Post) {
    if (!confirm(`Удалить «${p.title}»?`)) return
    try { await api.deletePost(p.id); showToast('Пост удалён', 'success'); load() }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  async function handlePublish(p: Post) {
    setPub(p.id)
    try { await api.publishPost(p.id); showToast('Пост опубликован!', 'success'); load() }
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
        <span className="ts tg" style={{ marginLeft: 'auto' }}>{filtered.length} постов</span>
        {canEdit && <button className="btn btn-primary" onClick={() => router.push('/posts/new')}>+ Создать пост</button>}
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
                  <td><span className={`sbadge ${SC[p.status]}`}>{DOT[p.status]} {SL[p.status]}</span></td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(p.platforms || []).map(pl => <span key={pl} className="pchip">{PI[pl] || pl} {pl.toUpperCase()}</span>)}
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
                      {canEdit && <button className="btn btn-secondary btn-sm" onClick={() => router.push(`/posts/${p.id}/edit`)}>✏</button>}
                      {canEdit && (p.status === 'draft' || p.status === 'scheduled') && (
                        <button className="btn btn-success btn-sm" onClick={() => handlePublish(p)} disabled={pub === p.id}>
                          {pub === p.id ? '...' : '↗'}
                        </button>
                      )}
                      {user?.role === 'admin' && (
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(p)}>×</button>
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
