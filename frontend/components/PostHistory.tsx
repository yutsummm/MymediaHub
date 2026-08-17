'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { PostHistoryEvent } from '@/lib/types'

/** Точка события: зелёная — состоялось, жёлтая — потребовало вмешательства. */
function dotClass(action: string): string {
  if (action === 'published' || action === 'post.approved') return 'timeline-dot ok'
  if (action === 'post.rejected' || action === 'removed') return 'timeline-dot warn'
  return 'timeline-dot'
}

const fmt = (s: string | null) => {
  if (!s) return ''
  const d = new Date(s)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
    + ', ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

/**
 * История поста: кто создал, кто отправил на согласование, кто вернул и с
 * каким замечанием, когда он вышел и когда его сняли.
 *
 * События уже пишутся в журнал действий — здесь их только показывают. Пока
 * этой ленты не было, замечание рецензента жило в одном уведомлении, которое
 * легко смахнуть и больше не найти.
 */
export default function PostHistory({ postId }: { postId: number }) {
  const [events, setEvents] = useState<PostHistoryEvent[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    api.getPostHistory(postId)
      .then(d => setEvents(d.events))
      .catch(() => setFailed(true))
  }, [postId])

  if (failed) return null

  return (
    <div className="card anim-in" style={{ marginTop: 16 }}>
      <div className="card-header">
        <span className="card-title">История</span>
      </div>
      <div style={{ padding: '16px 20px' }}>
        {events === null ? (
          <div style={{ color: 'var(--text-3)', fontSize: 13 }}>Загрузка...</div>
        ) : events.length === 0 ? (
          <div style={{ color: 'var(--text-3)', fontSize: 13 }}>Пока ничего не происходило</div>
        ) : (
          <div className="timeline">
            {events.map((e, i) => (
              <div className="timeline-row" key={i}>
                <span className={dotClass(e.action)} />
                <div>
                  <div className="timeline-ttl">{e.label}</div>
                  <div className="timeline-meta">
                    {fmt(e.at)}{e.actor ? ` · ${e.actor}` : ''}
                  </div>
                  {e.details && <div className="timeline-note">{e.details}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
