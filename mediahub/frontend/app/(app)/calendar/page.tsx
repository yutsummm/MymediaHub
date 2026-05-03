'use client'
import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { Post } from '@/lib/types'
import YandexLocationPickerModal from '@/components/YandexLocationPickerModal'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

const SDOT: Record<string, string> = { draft: '○', scheduled: '◑', published: '●' }

function pad(n: number) { return String(n).padStart(2, '0') }
function isoDate(d: Date) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) }

export default function CalendarPage() {
  const router = useRouter()
  const [cur, setCur] = useState<Date | null>(null)
  const [today, setToday] = useState<string>('')
  const [posts, setPosts] = useState<Post[]>([])
  const [loading, setLoading] = useState(true)
  const [pickerDate, setPickerDate] = useState<string | null>(null)

  useEffect(() => {
    const now = new Date()
    setCur(new Date(now.getFullYear(), now.getMonth(), 1))
    setToday(isoDate(now))
  }, [])

  useEffect(() => {
    if (!cur) return
    setLoading(true)
    const start = isoDate(new Date(cur.getFullYear(), cur.getMonth(), 1)) + 'T00:00'
    const end = isoDate(new Date(cur.getFullYear(), cur.getMonth() + 1, 0)) + 'T23:59'
    api.getCalendar(start, end)
      .then(d => setPosts(Array.isArray(d) ? d : []))
      .catch(e => { console.error(e); setPosts([]) })
      .finally(() => setLoading(false))
  }, [cur])

  const cells = useMemo(() => {
    if (!cur) return [] as (Date | null)[]
    const monthStart = new Date(cur.getFullYear(), cur.getMonth(), 1)
    const monthEnd = new Date(cur.getFullYear(), cur.getMonth() + 1, 0)
    const startDow = (monthStart.getDay() + 6) % 7
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

  if (!cur) {
    return (
      <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-3)' }}>
          <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.4 }}>◷</div>
          <div style={{ fontSize: 13, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600 }}>Загрузка</div>
        </div>
      </div>
    )
  }

  const monthLabel = `${MONTHS[cur.getMonth()]} ${cur.getFullYear()}`
  const totalInMonth = posts.length

  function openCreatePostForDate(date: string, address?: string, lat?: number | null, lng?: number | null) {
    const params = new URLSearchParams({
      status: 'scheduled',
      scheduled_at: `${date}T09:00`,
    })
    if (address) params.set('location_address', address)
    if (lat != null) params.set('location_lat', String(lat))
    if (lng != null) params.set('location_lng', String(lng))
    router.push(`/posts/new?${params.toString()}`)
  }

  return (
    <div className="content">
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20,
        padding: '14px 18px', background: 'var(--surface)',
        border: '1px solid var(--border)', borderRadius: 'var(--r-xl)',
      }}>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => setCur(new Date(cur.getFullYear(), cur.getMonth() - 1, 1))}
          aria-label="Предыдущий месяц"
        >←</button>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => setCur(new Date(cur.getFullYear(), cur.getMonth() + 1, 1))}
          aria-label="Следующий месяц"
        >→</button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            const n = new Date()
            setCur(new Date(n.getFullYear(), n.getMonth(), 1))
          }}
        >Сегодня</button>

        <div style={{
          fontWeight: 700, fontSize: 17, color: 'var(--text)',
          letterSpacing: '-0.02em', marginLeft: 8,
        }}>
          {monthLabel}
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-3)', fontWeight: 500 }}>
            {loading ? 'Загрузка...' : `${totalInMonth} постов`}
          </span>
          <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'var(--text-3)' }}>
            <span><span style={{ color: 'var(--text-2)' }}>○</span> Черновик</span>
            <span><span style={{ color: 'var(--yellow)' }}>◑</span> Запланирован</span>
            <span><span style={{ color: 'var(--green)' }}>●</span> Опубликован</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="cal-grid">
          {DAYS.map(d => <div key={d} className="cal-head">{d}</div>)}
          {cells.map((d, i) => {
            if (!d) return <div key={`e-${i}`} className="cal-cell other" />
            const ds = isoDate(d)
            const dp = postsByDay[ds] ?? []
            const isToday = ds === today
            return (
              <div
                key={ds}
                className={`cal-cell${isToday ? ' today' : ''}`}
                onClick={() => setPickerDate(ds)}
                role="button"
                tabIndex={0}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setPickerDate(ds)
                  }
                }}
                title="Создать пост на эту дату и выбрать адрес"
              >
                <div className="cal-date">{d.getDate()}</div>
                {dp.slice(0, 3).map(p => (
                  <div
                    key={p.id}
                    className={`cal-post cp-${p.status}`}
                    onClick={event => {
                      event.stopPropagation()
                      router.push(`/posts/${p.id}/edit`)
                    }}
                    title={p.title}
                  >
                    <span style={{ marginRight: 4, opacity: 0.7 }}>{SDOT[p.status]}</span>
                    {p.title}
                  </div>
                ))}
                {dp.length > 3 && (
                  <div
                    className="cal-more"
                    onClick={event => {
                      event.stopPropagation()
                      router.push(`/posts?date=${ds}`)
                    }}
                  >
                    +{dp.length - 3} ещё
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      <YandexLocationPickerModal
        open={pickerDate !== null}
        initialAddress=""
        initialLat={null}
        initialLng={null}
        onClose={() => setPickerDate(null)}
        onSelect={({ address, lat, lng }) => {
          const date = pickerDate
          setPickerDate(null)
          if (!date) return
          openCreatePostForDate(date, address, lat, lng)
        }}
      />
    </div>
  )
}
