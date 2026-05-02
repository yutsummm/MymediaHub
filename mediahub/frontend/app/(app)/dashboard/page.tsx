'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { AnalyticsSummary, Post } from '@/lib/types'

const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)
const fmtDate = (s: string | null) => {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
}

const STATUS_LABEL: Record<string, string> = { draft: 'Черновик', scheduled: 'Запланирован', published: 'Опубликован' }
const STATUS_CLASS: Record<string, string> = { draft: 's-draft', scheduled: 's-scheduled', published: 's-published' }

export default function DashboardPage() {
  const router = useRouter()
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [posts, setPosts] = useState<Post[]>([])

  useEffect(() => {
    api.getAnalyticsSummary().then(setSum).catch(console.error)
    api.getPosts({ limit: '5' } as never).then(d => setPosts(d.posts)).catch(console.error)
  }, [])

  if (!sum) {
    return (
      <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-3)' }}>
          <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.4 }}>◈</div>
          <div style={{ fontSize: 13, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600 }}>Загрузка</div>
        </div>
      </div>
    )
  }

  const cards = [
    { label: 'Всего постов',    val: sum.total_posts,              delta: '+12%', icon: '≡' },
    { label: 'Суммарный охват', val: fmtN(sum.total_views),        delta: '+18%', icon: '↗' },
    { label: 'Реакции',         val: fmtN(sum.total_reactions),    delta: '+9%',  icon: '♥' },
    { label: 'Вовлечённость',   val: sum.engagement_rate + '%',   delta: '+3%',  icon: '◎' },
  ]

  const statusRows = [
    { l: 'Опубликованы',  n: sum.published, c: 'var(--green)', pct: Math.round(sum.published / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Запланированы', n: sum.scheduled, c: 'var(--yellow)', pct: Math.round(sum.scheduled / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Черновики',     n: sum.drafts,    c: 'var(--text-3)', pct: Math.round(sum.drafts    / Math.max(sum.total_posts, 1) * 100) },
  ]

  return (
    <div className="content">

      {/* ── Stat cards ── */}
      <div className="stats-grid" style={{ marginBottom: 20 }}>
        {cards.map((c, i) => (
          <div key={i} className="stat-card anim-in">
            <div className="stat-icon" style={{ background: 'var(--accent-light)' }}>
              <span style={{ color: 'var(--accent)', fontSize: 15, fontWeight: 800 }}>
                {c.icon}
              </span>
            </div>
            <div className="stat-value">{c.val}</div>
            <div className="stat-label">{c.label}</div>
            <div className="stat-delta">↑ {c.delta} за месяц</div>
          </div>
        ))}
      </div>

      {/* ── Bento grid — asymmetric layout ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 340px',
        gridTemplateRows: 'auto auto',
        gap: 16,
      }}>

        {/* Recent posts — spans full height left */}
        <div className="card" style={{ gridRow: '1 / 3' }}>
          <div className="card-header">
            <span className="card-title">Последние посты</span>
            <button className="btn btn-ghost btn-sm" onClick={() => router.push('/posts')}
              style={{ fontSize: 11.5, letterSpacing: '0.04em' }}>
              Все посты →
            </button>
          </div>
          {posts.length === 0 && (
            <div className="empty">
              <div className="empty-ico">≡</div>
              <div>Нет постов</div>
            </div>
          )}
          {posts.map(p => (
            <div
              key={p.id}
              onClick={() => router.push(`/posts/${p.id}/edit`)}
              style={{
                padding: '14px 22px',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 14,
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-h)')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontWeight: 600, fontSize: 13, letterSpacing: '-0.01em', marginBottom: 3 }}>
                  {p.title}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 500 }}>
                  {fmtDate(p.created_at)}
                </div>
              </div>
              <span className={`sbadge ${STATUS_CLASS[p.status]}`}>
                {STATUS_LABEL[p.status]}
              </span>
            </div>
          ))}
        </div>

        {/* Publication status */}
        <div className="card card-p">
          <div className="card-title" style={{ marginBottom: 18 }}>Статус публикаций</div>
          {statusRows.map(s => (
            <div key={s.l} style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 6, fontWeight: 500 }}>
                <span style={{ color: 'var(--text-2)' }}>{s.l}</span>
                <span style={{ fontWeight: 800, color: 'var(--text)', fontSize: 13 }}>{s.n}</span>
              </div>
              <div className="pbar">
                <div className="pfill" style={{ width: s.pct + '%', background: s.c }} />
              </div>
            </div>
          ))}
        </div>

        {/* Top posts */}
        <div className="card card-p">
          <div className="card-title" style={{ marginBottom: 16 }}>Топ постов</div>
          {sum.top_posts.slice(0, 3).map((p, i) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div style={{
                width: 24, height: 24,
                borderRadius: 6,
                background: i === 0 ? 'var(--accent)' : 'var(--surface-2)',
                color: i === 0 ? 'var(--btn-primary-fg)' : 'var(--text-3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 800, flexShrink: 0,
              }}>
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 2, letterSpacing: '-0.01em' }}>
                  {p.title}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {fmtN(p.views)} просм · {p.reactions} реакций
                </div>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  )
}
