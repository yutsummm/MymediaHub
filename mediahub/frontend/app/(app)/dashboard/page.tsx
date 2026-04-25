'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { AnalyticsSummary, Post } from '@/lib/types'

const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)
const fmtDate = (s: string | null) => {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
}
const SL: Record<string, string> = { draft: 'Черновик', scheduled: 'Запланирован', published: 'Опубликован' }
const SC: Record<string, string> = { draft: 's-draft', scheduled: 's-scheduled', published: 's-published' }
const DOT: Record<string, string> = { draft: '○', scheduled: '◑', published: '●' }

export default function DashboardPage() {
  const router = useRouter()
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [posts, setPosts] = useState<Post[]>([])

  useEffect(() => {
    api.getAnalyticsSummary().then(setSum).catch(console.error)
    api.getPosts({ limit: '5' } as never).then(d => setPosts(d.posts)).catch(console.error)
  }, [])

  if (!sum) return <div className="content">⏳ Загрузка...</div>

  const cards = [
    { icon: '📝', label: 'Всего постов',    val: sum.total_posts,                    bg: '#eff6ff' },
    { icon: '👁',  label: 'Суммарный охват', val: fmtN(sum.total_views),              bg: '#f0fdf4' },
    { icon: '❤️', label: 'Реакции',         val: fmtN(sum.total_reactions),          bg: '#fff7ed' },
    { icon: '📊', label: 'Вовлечённость',   val: sum.engagement_rate + '%',          bg: '#fdf4ff' },
  ]

  const statusRows = [
    { l: 'Опубликованы',  n: sum.published, c: '#16a34a', pct: Math.round(sum.published / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Запланированы', n: sum.scheduled, c: '#d97706', pct: Math.round(sum.scheduled / Math.max(sum.total_posts, 1) * 100) },
    { l: 'Черновики',     n: sum.drafts,    c: '#6b7280', pct: Math.round(sum.drafts    / Math.max(sum.total_posts, 1) * 100) },
  ]

  return (
    <div className="content">
      <div className="stats-grid">
        {cards.map((c, i) => (
          <div key={i} className="stat-card">
            <div className="stat-icon" style={{ background: c.bg }}>{c.icon}</div>
            <div className="stat-value">{c.val}</div>
            <div className="stat-label">{c.label}</div>
            <div className="stat-delta">↑ +12% за месяц</div>
          </div>
        ))}
      </div>

      <div className="grid2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">📋 Последние посты</span>
            <button className="btn btn-ghost btn-sm" onClick={() => router.push('/posts')}>Все →</button>
          </div>
          {posts.map(p => (
            <div key={p.id} style={{ padding: '12px 20px', borderBottom: '1px solid var(--gray-100)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
              onClick={() => router.push(`/posts/${p.id}/edit`)}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontWeight: 600, fontSize: 14 }}>{p.title}</div>
                <div style={{ fontSize: 11, color: 'var(--gray-400)', marginTop: 3 }}>{fmtDate(p.created_at)}</div>
              </div>
              <span className={`sbadge ${SC[p.status]}`}>{DOT[p.status]} {SL[p.status]}</span>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card card-p">
            <div className="card-title" style={{ marginBottom: 14 }}>📊 Статус публикаций</div>
            {statusRows.map(s => (
              <div key={s.l} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                  <span>{s.l}</span><span style={{ fontWeight: 700 }}>{s.n}</span>
                </div>
                <div className="pbar"><div className="pfill" style={{ width: s.pct + '%', background: s.c }} /></div>
              </div>
            ))}
          </div>

          <div className="card card-p">
            <div className="card-title" style={{ marginBottom: 12 }}>🏆 Топ постов</div>
            {sum.top_posts.slice(0, 3).map((p, i) => (
              <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <div style={{ width: 22, height: 22, borderRadius: 4, background: ['#fbbf24', '#9ca3af', '#cd7c2f'][i], color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>{i + 1}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="trunc" style={{ fontSize: 13, fontWeight: 600 }}>{p.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>👁 {fmtN(p.views)} · ❤️ {p.reactions}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
