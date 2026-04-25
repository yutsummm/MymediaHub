'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { Post } from '@/lib/types'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function startOfMonth(d: Date) { return new Date(d.getFullYear(), d.getMonth(), 1) }
function endOfMonth(d: Date)   { return new Date(d.getFullYear(), d.getMonth() + 1, 0) }

function isoDate(d: Date) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

export default function CalendarPage() {
  const router = useRouter()
  const [cur, setCur] = useState(new Date())
  const [posts, setPosts] = useState<Post[]>([])

  useEffect(() => {
    const s = startOfMonth(cur); const e = endOfMonth(cur)
    api.getCalendar(isoDate(s) + 'T00:00', isoDate(e) + 'T23:59')
      .then(setPosts).catch(console.error)
  }, [cur])

  const monthStart = startOfMonth(cur)
  const monthEnd   = endOfMonth(cur)

  // pad to Mon-start grid
  const startDow = (monthStart.getDay() + 6) % 7
  const cells: (Date | null)[] = [...Array(startDow).fill(null)]
  for (let d = 1; d <= monthEnd.getDate(); d++) {
    cells.push(new Date(cur.getFullYear(), cur.getMonth(), d))
  }
  while (cells.length % 7 !== 0) cells.push(null)

  const today = isoDate(new Date())

  function postsForDay(d: Date) {
    const ds = isoDate(d)
    return posts.filter(p => {
      const dt = p.scheduled_at ?? p.published_at ?? p.created_at
      return dt?.startsWith(ds)
    })
  }

  const monthLabel = cur.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })

  return (
    <div className="content">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <button className="btn btn-secondary btn-sm" onClick={() => setCur(new Date(cur.getFullYear(), cur.getMonth() - 1, 1))}>←</button>
        <span style={{ fontWeight: 700, fontSize: 16, textTransform: 'capitalize', minWidth: 160, textAlign: 'center' }}>{monthLabel}</span>
        <button className="btn btn-secondary btn-sm" onClick={() => setCur(new Date(cur.getFullYear(), cur.getMonth() + 1, 1))}>→</button>
        <button className="btn btn-ghost btn-sm" onClick={() => setCur(new Date())}>Сегодня</button>
      </div>

      <div className="card">
        <div className="cal-grid">
          {DAYS.map(d => <div key={d} className="cal-head">{d}</div>)}
          {cells.map((d, i) => {
            if (!d) return <div key={i} className="cal-cell other" />
            const ds = isoDate(d)
            const dp = postsForDay(d)
            return (
              <div key={i} className={`cal-cell${ds === today ? ' today' : ''}`}>
                <div className="cal-date">{d.getDate()}</div>
                {dp.slice(0, 3).map(p => (
                  <div key={p.id} className={`cal-post cp-${p.status}`}
                    onClick={() => router.push(`/posts/${p.id}/edit`)} title={p.title}>
                    {p.title}
                  </div>
                ))}
                {dp.length > 3 && <div className="cal-more">+{dp.length - 3} ещё</div>}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
