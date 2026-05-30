'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import QuickPostModal from '@/components/QuickPostModal'
import type { AnalyticsSummary, Post } from '@/lib/types'

const fmtN = (n: number) => n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + 'M' : n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)
const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' }) : '—'

const STATUS_LABEL: Record<string, string> = { draft: 'Черновик', scheduled: 'Запланирован', published: 'Опубликован' }
const STATUS_CLASS: Record<string, string> = { draft: 's-draft', scheduled: 's-scheduled', published: 's-published' }

const S = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const Sm = { ...S, width: 16, height: 16 }

const DASH_ICONS = [
  <svg key="posts" {...S}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>,
  <svg key="views" {...S}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  <svg key="heart" {...S}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>,
  <svg key="trend" {...S}><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>,
]


function useCountUp(target: number, duration = 700): number {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (target === 0) { setVal(0); return }
    let raf: number
    const start = Date.now()
    const tick = () => {
      const p = Math.min((Date.now() - start) / duration, 1)
      const eased = 1 - (1 - p) ** 3
      setVal(Math.round(eased * target))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return val
}

function StatCard({ label, raw, fmt, icon, index }: {
  label: string; raw: number; fmt: (n: number) => string; icon: React.ReactNode; index: number
}) {
  const animated = useCountUp(raw)
  return (
    <div className="stat-card anim-in" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="stat-top">
        <div className="stat-label">{label}</div>
        <div className="stat-icon">{icon}</div>
      </div>
      <div className="stat-value">{fmt(animated)}</div>
      <div className="stat-delta">
        {raw > 0 ? 'Данные из VK' : 'Нет данных'}
      </div>
    </div>
  )
}

function SkeletonStatCard({ index }: { index: number }) {
  return (
    <div className="stat-card anim-in" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="stat-top">
        <div className="skeleton skeleton-text" style={{ width: 80 }} />
        <div className="skeleton" style={{ width: 18, height: 18, borderRadius: 4 }} />
      </div>
      <div className="skeleton skeleton-title" style={{ width: 70, marginTop: 14 }} />
      <div className="skeleton skeleton-text" style={{ width: 100, marginTop: 10 }} />
    </div>
  )
}

export default function DashboardPage() {
  const router = useRouter()
  const { user } = useAuth()
  const { currentGroup } = useGroup()
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [posts, setPosts] = useState<Post[] | null>(null)
  const [quickModal, setQuickModal] = useState(false)

  const canEdit = (currentGroup?.role ?? user?.role) !== 'observer'

  useEffect(() => {
    api.getAnalyticsSummary().then(setSum).catch(console.error)
    api.getPosts({ limit: '5' } as never).then(d => setPosts(d.posts)).catch(console.error)
    // Sync real VK stats on dashboard load
    api.syncVkStats().catch(() => {})
  }, [])

  const cards = sum ? [
    { label: 'Всего постов',    raw: sum.total_posts,   fmt: (n: number) => String(n) },
    { label: 'Суммарный охват', raw: sum.total_views,   fmt: fmtN },
    { label: 'Реакции',         raw: sum.total_reactions, fmt: fmtN },
    { label: 'Вовлечённость',   raw: Math.round(sum.engagement_rate * 10), fmt: (n: number) => (n / 10).toFixed(1) + '%' },
  ] : []

  const statusRows = sum ? [
    { l: 'Опубликованы',  n: sum.published, c: 'var(--green)',  pct: Math.round(sum.published / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Запланированы', n: sum.scheduled, c: 'var(--yellow)', pct: Math.round(sum.scheduled / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Черновики',     n: sum.drafts,    c: 'var(--text-3)', pct: Math.round(sum.drafts    / Math.max(sum.total_posts, 1) * 100) },
  ] : []

  return (
    <div className="content">
      {quickModal && <QuickPostModal onClose={() => setQuickModal(false)} />}

      {/* Stat cards */}
      <div className="stats-grid" style={{ marginBottom: 20 }}>
        {sum
          ? cards.map((c, i) => (
              <StatCard key={i} index={i} label={c.label} raw={c.raw} fmt={c.fmt} icon={DASH_ICONS[i]} />
            ))
          : [0,1,2,3].map(i => <SkeletonStatCard key={i} index={i} />)
        }
      </div>

      {/* Bento grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>

        {/* Recent posts */}
        <div className="card" style={{ gridRow: '1 / 3' }}>
          <div className="card-header">
            <span className="card-title">Последние посты</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {canEdit && (
                <button className="btn btn-primary btn-sm" onClick={() => setQuickModal(true)}>
                  <svg {...Sm}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                  Черновик
                </button>
              )}
              <button className="btn btn-ghost btn-sm" onClick={() => router.push('/posts')} style={{ fontSize: 11.5 }}>
                Все посты →
              </button>
            </div>
          </div>

          {posts === null ? (
            [0,1,2,3,4].map(i => (
              <div key={i} style={{ padding: '14px 22px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ flex: 1 }}>
                  <div className="skeleton skeleton-text" style={{ width: '65%', marginBottom: 8 }} />
                  <div className="skeleton skeleton-text" style={{ width: 60 }} />
                </div>
                <div className="skeleton" style={{ width: 72, height: 20, borderRadius: 20 }} />
              </div>
            ))
          ) : posts.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
              </div>
              <div className="empty-state-title">Постов пока нет</div>
              <div className="empty-state-sub">Создайте первый пост и начните публиковать контент в соцсети</div>
              {canEdit && (
                <button className="btn btn-primary btn-sm" onClick={() => setQuickModal(true)} style={{ marginTop: 4 }}>
                  + Создать пост
                </button>
              )}
            </div>
          ) : posts.map((p, i) => (
            <div
              key={p.id}
              className="anim-in"
              onClick={() => router.push(`/posts/${p.id}/edit`)}
              style={{
                padding: '14px 22px', borderBottom: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14,
                cursor: 'pointer', transition: 'background var(--dur-fast) var(--ease-out)',
                animationDelay: `${i * 40}ms`,
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
                  {p.author_name && ` · ${p.author_name}`}
                </div>
              </div>
              <span className={`sbadge ${STATUS_CLASS[p.status]}`}>{STATUS_LABEL[p.status]}</span>
            </div>
          ))}
        </div>

        {/* Publication status */}
        <div className="card card-p anim-in" style={{ animationDelay: '80ms' }}>
          <div className="card-title" style={{ marginBottom: 20 }}>Статус публикаций</div>
          {sum === null ? (
            [0,1,2].map(i => (
              <div key={i} style={{ marginBottom: 18 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div className="skeleton skeleton-text" style={{ width: 90 }} />
                  <div className="skeleton skeleton-text" style={{ width: 20 }} />
                </div>
                <div className="skeleton" style={{ height: 3, width: '100%', borderRadius: 4 }} />
              </div>
            ))
          ) : statusRows.map(s => (
            <div key={s.l} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 7, fontWeight: 500 }}>
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
        <div className="card card-p anim-in" style={{ animationDelay: '120ms' }}>
          <div className="card-title" style={{ marginBottom: 16 }}>Топ постов</div>
          {sum === null ? (
            [0,1,2].map(i => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                <div className="skeleton" style={{ width: 26, height: 26, borderRadius: 6, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton skeleton-text" style={{ width: '80%', marginBottom: 6 }} />
                  <div className="skeleton skeleton-text" style={{ width: '50%' }} />
                </div>
              </div>
            ))
          ) : sum.top_posts.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '12px 0 4px', color: 'var(--text-3)', fontSize: 12, lineHeight: 1.7 }}>
              Данные появятся<br/>после первых публикаций
            </div>
          ) : sum.top_posts.slice(0, 3).map((p, i) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, cursor: 'pointer' }}
              onClick={() => router.push(`/posts/${p.id}/edit`)}
            >
              <div style={{
                width: 26, height: 26, borderRadius: 6, flexShrink: 0,
                background: i === 0 ? 'var(--accent)' : 'var(--surface-2)',
                color: i === 0 ? 'var(--btn-primary-fg)' : 'var(--text-3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 800,
              }}>
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 2 }}>{p.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{fmtN(p.views)} просм · {p.reactions} реакций</div>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  )
}
