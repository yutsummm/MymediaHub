'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import QuickPostModal from '@/components/QuickPostModal'
import type { AnalyticsSummary, Post } from '@/lib/types'

/* ─── Formatters ─── */
const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)
const fmtDate = (s: string | null) => {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
}

const STATUS_LABEL: Record<string, string> = { draft: 'Черновик', scheduled: 'Запланирован', published: 'Опубликован' }
const STATUS_CLASS: Record<string, string> = { draft: 's-draft', scheduled: 's-scheduled', published: 's-published' }

/* ─── SVG props ─── */
const S18 = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const S16 = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const DASH_ICONS = [
  <svg key="posts" {...S18}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>,
  <svg key="views" {...S18}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  <svg key="heart" {...S18}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>,
  <svg key="trend" {...S18}><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>,
]

/* ─── Deterministic sparkline (seed → smooth upward trend) ─── */
function genSparkline(seed: number, count = 7): number[] {
  return Array.from({ length: count }, (_, i) => {
    const noise = Math.abs(Math.sin(seed * 3.71 + i * 1.93)) * 0.26
    const trend = (i / (count - 1)) * 0.55
    return Math.min(0.96, Math.max(0.08, 0.14 + trend + noise))
  })
}

function Sparkline({ seed }: { seed: number }) {
  const W = 64, H = 24
  const pts = genSparkline(seed)
  const xs  = pts.map((_, i) => (i / (pts.length - 1)) * W)
  const ys  = pts.map(v => H - v * H)
  const d   = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} fill="none" style={{ display: 'block' }}>
      <path d={d} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/* ─── Animated counter (ease-out cubic) ─── */
function useCountUp(target: number, duration = 720): number {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (target === 0) { setVal(0); return }
    let raf: number
    const start = Date.now()
    const tick = () => {
      const p      = Math.min((Date.now() - start) / duration, 1)
      const eased  = 1 - (1 - p) ** 3
      setVal(Math.round(eased * target))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return val
}

/* ─── Stat card with counter + sparkline ─── */
function StatCard({
  label, raw, fmt, delta, icon, index,
}: {
  label: string
  raw: number
  fmt: (n: number) => string
  delta: string
  icon: React.ReactNode
  index: number
}) {
  const animated = useCountUp(raw)
  return (
    <div className="stat-card anim-in" style={{ animationDelay: `${index * 40}ms` }}>
      <div className="stat-top">
        <div className="stat-label">{label}</div>
        <div className="stat-icon">{icon}</div>
      </div>
      <div className="stat-value">{fmt(animated)}</div>
      <div className="stat-delta">↑ {delta} за месяц</div>
      <div className="sparkline-wrap">
        <Sparkline seed={index * 7.3 + raw * 0.01} />
      </div>
    </div>
  )
}

/* ─── Empty posts state ─── */
function EmptyPosts({ onNew }: { onNew: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <line x1="10" y1="9" x2="8" y2="9"/>
        </svg>
      </div>
      <div className="empty-state-title">Постов пока нет</div>
      <div className="empty-state-sub">
        Создайте первый пост и начните публиковать контент в соцсети
      </div>
      <button className="btn btn-primary btn-sm" onClick={onNew} style={{ marginTop: 4 }}>
        + Создать пост
      </button>
    </div>
  )
}

/* ─── Page ─── */
export default function DashboardPage() {
  const router          = useRouter()
  const { user }        = useAuth()
  const { currentGroup } = useGroup()
  const [sum, setSum]   = useState<AnalyticsSummary | null>(null)
  const [posts, setPosts] = useState<Post[]>([])
  const [quickModal, setQuickModal] = useState(false)

  const canEdit = (currentGroup?.role ?? user?.role) !== 'observer'

  useEffect(() => {
    api.getAnalyticsSummary().then(setSum).catch(console.error)
    api.getPosts({ limit: '5' } as never).then(d => setPosts(d.posts)).catch(console.error)
  }, [])

  /* Loading skeleton */
  if (!sum) {
    return (
      <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-3)' }}>
          <div style={{ marginBottom: 14, opacity: 0.2 }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </div>
          <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 700 }}>Загрузка</div>
        </div>
      </div>
    )
  }

  /* engagement_rate comes as float e.g. 9.8 — multiply ×10 so counter animates in 0.1 steps */
  const cards = [
    { label: 'Всего постов',    raw: sum.total_posts,             fmt: (n: number) => String(n),                  delta: '+12%' },
    { label: 'Суммарный охват', raw: sum.total_views,             fmt: fmtN,                                      delta: '+18%' },
    { label: 'Реакции',         raw: sum.total_reactions,         fmt: fmtN,                                      delta: '+9%'  },
    { label: 'Вовлечённость',   raw: Math.round(sum.engagement_rate * 10), fmt: (n: number) => (n / 10).toFixed(1) + '%', delta: '+3%'  },
  ]

  const statusRows = [
    { l: 'Опубликованы',  n: sum.published, c: 'var(--green)',  pct: Math.round(sum.published / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Запланированы', n: sum.scheduled, c: 'var(--yellow)', pct: Math.round(sum.scheduled / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Черновики',     n: sum.drafts,    c: 'var(--text-3)', pct: Math.round(sum.drafts    / Math.max(sum.total_posts, 1) * 100) },
  ]

  return (
    <div className="content">
      {quickModal && <QuickPostModal onClose={() => setQuickModal(false)} />}

      {/* ── Stat cards ── */}
      <div className="stats-grid" style={{ marginBottom: 20 }}>
        {cards.map((c, i) => (
          <StatCard key={i} index={i} label={c.label} raw={c.raw} fmt={c.fmt} delta={c.delta} icon={DASH_ICONS[i]} />
        ))}
      </div>

      {/* ── Bento grid ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gridTemplateRows: 'auto auto', gap: 16 }}>

        {/* Recent posts — spans full height left */}
        <div className="card" style={{ gridRow: '1 / 3' }}>
          <div className="card-header">
            <span className="card-title">Последние посты</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {canEdit && (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setQuickModal(true)}
                  style={{ gap: 6 }}
                >
                  <svg {...S16}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                  Быстрый черновик
                </button>
              )}
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => router.push('/posts')}
                style={{ fontSize: 11.5, letterSpacing: '0.04em' }}
              >
                Все посты →
              </button>
            </div>
          </div>

          {posts.length === 0
            ? <EmptyPosts onNew={() => canEdit ? setQuickModal(true) : router.push('/posts')} />
            : posts.map(p => (
              <div
                key={p.id}
                onClick={() => router.push(`/posts/${p.id}/edit`)}
                style={{
                  padding: '14px 22px',
                  borderBottom: '1px solid var(--border)',
                  display: 'flex', alignItems: 'center',
                  justifyContent: 'space-between', gap: 14,
                  cursor: 'pointer', transition: 'background 0.15s',
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
            ))
          }
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
          {sum.top_posts.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '18px 0 6px', color: 'var(--text-3)', fontSize: 12, lineHeight: 1.6 }}>
              Данные появятся<br/>после первых публикаций
            </div>
          ) : sum.top_posts.slice(0, 3).map((p, i) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div style={{
                width: 24, height: 24, borderRadius: 6,
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
