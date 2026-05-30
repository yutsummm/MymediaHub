'use client'
import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { Post } from '@/lib/types'
import QuickPostModal from '@/components/QuickPostModal'
import ConfirmDialog from '@/components/ConfirmDialog'

const DAYS   = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

const STATUS_COLOR: Record<string, string> = {
  draft:     'var(--text-3)',
  scheduled: 'var(--yellow)',
  published: 'var(--green)',
}

const PLATFORM_LABEL: Record<string, string> = { vk: 'ВК', telegram: 'TG' }

function pad(n: number) { return String(n).padStart(2, '0') }
function isoDate(d: Date) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) }
function fmtTime(s: string) {
  return new Date(s).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export default function CalendarPage() {
  const router = useRouter()
  const [cur, setCur]           = useState<Date | null>(null)
  const [today, setToday]       = useState<string>('')
  const [posts, setPosts]       = useState<Post[]>([])
  const [loading, setLoading]   = useState(true)
  const [quickDate, setQuickDate] = useState<string | null>(null)
  const [dragPost, setDragPost] = useState<Post | null>(null)
  const [dragOver, setDragOver] = useState<string | null>(null)
  const [pendingDrop, setPendingDrop] = useState<{ post: Post; date: string } | null>(null)

  useEffect(() => {
    const now = new Date()
    setCur(new Date(now.getFullYear(), now.getMonth(), 1))
    setToday(isoDate(now))
  }, [])

  function loadPosts() {
    if (!cur) return
    setLoading(true)
    const start = isoDate(new Date(cur.getFullYear(), cur.getMonth(), 1)) + 'T00:00'
    const end   = isoDate(new Date(cur.getFullYear(), cur.getMonth() + 1, 0)) + 'T23:59'
    api.getCalendar(start, end)
      .then(d => setPosts(Array.isArray(d) ? d : []))
      .catch(e => { console.error(e); setPosts([]) })
      .finally(() => setLoading(false))
  }

  useEffect(loadPosts, [cur])

  const cells = useMemo(() => {
    if (!cur) return [] as (Date | null)[]
    const monthStart = new Date(cur.getFullYear(), cur.getMonth(), 1)
    const monthEnd   = new Date(cur.getFullYear(), cur.getMonth() + 1, 0)
    const startDow   = (monthStart.getDay() + 6) % 7
    const arr: (Date | null)[] = Array(startDow).fill(null)
    for (let d = 1; d <= monthEnd.getDate(); d++) arr.push(new Date(cur.getFullYear(), cur.getMonth(), d))
    while (arr.length % 7 !== 0) arr.push(null)
    return arr
  }, [cur])

  const postsByDay = useMemo(() => {
    const map: Record<string, Post[]> = {}
    for (const p of posts) {
      const dt = p.scheduled_at ?? p.published_at ?? p.created_at
      if (!dt) continue
      const ds = dt.slice(0, 10)
      if (!map[ds]) map[ds] = []
      map[ds].push(p)
    }
    return map
  }, [posts])

  async function handleDrop(targetDate: string) {
    if (!dragPost) return
    setPendingDrop({ post: dragPost, date: targetDate })
    setDragPost(null); setDragOver(null)
  }

  async function confirmDrop() {
    if (!pendingDrop) return
    const { post, date: targetDate } = pendingDrop
    const existingDt = post.scheduled_at ?? post.published_at ?? ''
    const time = existingDt ? existingDt.slice(11, 16) : '09:00'
    try {
      await api.updatePost(post.id, { scheduled_at: `${targetDate}T${time}`, status: 'scheduled' })
      loadPosts()
    } catch (e) { console.error(e) }
    setPendingDrop(null)
  }

  if (!cur) return (
    <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-3)', fontSize: 12, fontWeight: 600 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'spin 0.7s linear infinite' }}>
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
        </svg>
        Загрузка...
      </div>
    </div>
  )

  const monthLabel  = `${MONTHS[cur.getMonth()]} ${cur.getFullYear()}`
  const totalInMonth = posts.length
  const prevMonth = () => setCur(new Date(cur.getFullYear(), cur.getMonth() - 1, 1))
  const nextMonth = () => setCur(new Date(cur.getFullYear(), cur.getMonth() + 1, 1))

  return (
    <div className="content">
      {quickDate && (
        <QuickPostModal scheduledDate={quickDate} onClose={() => setQuickDate(null)} onSaved={loadPosts} />
      )}

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 16, flexWrap: 'wrap', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', borderRadius: 'var(--r-md)', overflow: 'hidden', border: '1px solid var(--border)' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={prevMonth}
              style={{ borderRadius: 0, border: 'none', borderRight: '1px solid var(--border)', padding: '6px 12px' }}
              aria-label="Предыдущий месяц"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={nextMonth}
              style={{ borderRadius: 0, border: 'none', padding: '6px 12px' }}
              aria-label="Следующий месяц"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>

          <button
            className="btn btn-secondary btn-sm"
            onClick={() => { const n = new Date(); setCur(new Date(n.getFullYear(), n.getMonth(), 1)) }}
          >
            Сегодня
          </button>

          <h2 style={{ fontSize: 18, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.04em', marginLeft: 4 }}>
            {monthLabel}
          </h2>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 600 }}>
            {loading ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                Загрузка...
              </span>
            ) : `${totalInMonth} постов`}
          </span>
          <div style={{ display: 'flex', gap: 10, fontSize: 11.5, color: 'var(--text-3)' }}>
            {(['draft', 'scheduled', 'published'] as const).map((s, i) => (
              <span key={s} style={{ display: 'flex', alignItems: 'center', gap: 5, fontWeight: 500 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_COLOR[s], display: 'inline-block', flexShrink: 0 }} />
                {['Черновик', 'Запланирован', 'Опубликован'][i]}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Calendar grid */}
      <div className="card">
        <div className="cal-grid">
          {DAYS.map((d, i) => (
            <div key={d} className={`cal-head${i >= 5 ? ' weekend' : ''}`}>{d}</div>
          ))}

          {cells.map((d, i) => {
            if (!d) return <div key={`e-${i}`} className="cal-cell other" />
            const ds       = isoDate(d)
            const dp       = postsByDay[ds] ?? []
            const isToday  = ds === today
            const isWeekend = d.getDay() === 0 || d.getDay() === 6
            const colIdx   = i % 7
            const isDragTarget = dragOver === ds

            return (
              <div
                key={ds}
                className={['cal-cell', isToday ? 'today' : '', isWeekend ? 'weekend' : '', isDragTarget ? 'drag-over' : ''].filter(Boolean).join(' ')}
                onClick={() => setQuickDate(ds)}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setQuickDate(ds) } }}
                onDragOver={e => { e.preventDefault(); setDragOver(ds) }}
                onDragLeave={() => setDragOver(null)}
                onDrop={e => { e.preventDefault(); handleDrop(ds) }}
              >
                <div className="cal-date">{d.getDate()}</div>

                {dp.slice(0, 3).map(p => {
                  const dateStr = p.scheduled_at ?? p.published_at ?? p.created_at
                  return (
                    <div key={p.id} className="cal-post-wrap">
                      <div
                        className={`cal-post cp-${p.status}`}
                        draggable
                        onDragStart={e => { e.stopPropagation(); setDragPost(p) }}
                        onDragEnd={() => { setDragPost(null); setDragOver(null) }}
                        onClick={e => { e.stopPropagation(); router.push(`/posts/${p.id}/edit`) }}
                      >
                        <span className="cal-post-dot" style={{ background: STATUS_COLOR[p.status] }} />
                        <span className="cal-post-title">{p.title}</span>
                        {(p.platforms || []).slice(0, 1).map(pl => (
                          <span key={pl} className="cal-post-platform">{PLATFORM_LABEL[pl] || pl}</span>
                        ))}
                      </div>
                      <div className={`cal-tooltip${colIdx >= 5 ? ' right' : ''}`}>
                        <div className="cal-tooltip-title">{p.title}</div>
                        {p.content && <div className="cal-tooltip-content">{p.content}</div>}
                        <div className="cal-tooltip-meta">
                          {dateStr && <span className="cal-tooltip-time">{fmtTime(dateStr)}</span>}
                          {(p.platforms || []).map(pl => (
                            <span key={pl} className="cal-tooltip-platform">{PLATFORM_LABEL[pl] || pl}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )
                })}

                {dp.length > 3 && (
                  <div className="cal-more" onClick={e => { e.stopPropagation(); router.push(`/posts?date=${ds}`) }}>
                    +{dp.length - 3} ещё
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDrop !== null}
        title="Перенести пост?"
        description={pendingDrop ? `Изменить дату поста «${pendingDrop.post.title}» на ${new Date(pendingDrop.date + 'T12:00').toLocaleDateString('ru-RU', { day: '2-digit', month: 'long' })}?` : ''}
        variant="warning"
        confirmLabel="Перенести"
        onConfirm={confirmDrop}
        onCancel={() => { setPendingDrop(null); setDragOver(null) }}
      />
    </div>
  )
}
