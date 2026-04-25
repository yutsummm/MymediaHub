'use client'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { AnalyticsSummary, TimelinePoint } from '@/lib/types'

declare const Chart: typeof import('chart.js').Chart

const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)

export default function AnalyticsPage() {
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [tl, setTl] = useState<TimelinePoint[]>([])
  const [period, setPeriod] = useState('month')
  const lineRef  = useRef<HTMLCanvasElement>(null)
  const lineChart = useRef<InstanceType<typeof Chart> | null>(null)
  const barRef   = useRef<HTMLCanvasElement>(null)
  const barChart  = useRef<InstanceType<typeof Chart> | null>(null)

  useEffect(() => { api.getAnalyticsSummary().then(setSum).catch(console.error) }, [])
  useEffect(() => { api.getTimeline(period).then(setTl).catch(console.error) }, [period])

  useEffect(() => {
    if (!tl.length || !lineRef.current) return
    lineChart.current?.destroy()
    // @ts-expect-error Chart.js loaded via CDN
    lineChart.current = new window.Chart(lineRef.current.getContext('2d'), {
      type: 'line',
      data: {
        labels: tl.map(d => d.label),
        datasets: [
          { label: 'Просмотры', data: tl.map(d => d.views),     borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,.1)', tension: .4, fill: true },
          { label: 'Реакции',   data: tl.map(d => d.reactions), borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,.08)', tension: .4 },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: { y: { beginAtZero: true } } },
    })
    return () => { lineChart.current?.destroy() }
  }, [tl])

  useEffect(() => {
    if (!sum?.platform_stats || !barRef.current) return
    barChart.current?.destroy()
    const d = sum.platform_stats
    // @ts-expect-error Chart.js loaded via CDN
    barChart.current = new window.Chart(barRef.current.getContext('2d'), {
      type: 'bar',
      data: {
        labels: d.map(x => x.platform.toUpperCase()),
        datasets: [
          { label: 'Постов',           data: d.map(x => x.count),                    backgroundColor: '#2563eb' },
          { label: 'Просмотры (÷100)', data: d.map(x => Math.round(x.views / 100)), backgroundColor: '#16a34a' },
          { label: 'Реакции',          data: d.map(x => x.reactions),                backgroundColor: '#d97706' },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } } },
    })
    return () => { barChart.current?.destroy() }
  }, [sum])

  if (!sum) return <div className="content">⏳ Загрузка...</div>

  const mc = [
    { icon: '👁',  l: 'Просмотров',   v: fmtN(sum.total_views) },
    { icon: '❤️', l: 'Реакций',       v: fmtN(sum.total_reactions) },
    { icon: '💬', l: 'Комментариев',  v: fmtN(sum.total_comments) },
    { icon: '🔁', l: 'Репостов',      v: fmtN(sum.total_shares) },
  ]

  return (
    <div className="content">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" async />

      <div className="grid4" style={{ marginBottom: 24 }}>
        {mc.map((c, i) => (
          <div key={i} className="stat-card">
            <div className="stat-icon" style={{ background: 'var(--blue-light)' }}>{c.icon}</div>
            <div className="stat-value">{c.v}</div>
            <div className="stat-label">{c.l}</div>
          </div>
        ))}
      </div>

      <div className="card mb6">
        <div className="card-header">
          <span className="card-title">📈 Динамика охватов</span>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['week', 'month', 'quarter'] as const).map(p => (
              <button key={p} className={`btn btn-sm ${period === p ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setPeriod(p)}>
                {{ week: 'Неделя', month: 'Месяц', quarter: 'Квартал' }[p]}
              </button>
            ))}
          </div>
        </div>
        <div style={{ padding: 20 }}>
          <div className="chart-box"><canvas ref={lineRef} /></div>
        </div>
      </div>

      <div className="grid2">
        <div className="card">
          <div className="card-header"><span className="card-title">📊 Сравнение площадок</span></div>
          <div style={{ padding: 20 }}>
            <div className="chart-box" style={{ height: 200 }}><canvas ref={barRef} /></div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">🏆 Топ-5 постов</span></div>
          {sum.top_posts.map((p, i) => (
            <div key={p.id} style={{ padding: '12px 20px', borderBottom: '1px solid var(--gray-100)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 26, height: 26, borderRadius: 6, background: ['#fbbf24', '#9ca3af', '#cd7c2f', '#e5e7eb', '#e5e7eb'][i], color: i < 3 ? '#fff' : 'var(--gray-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 800, flexShrink: 0 }}>{i + 1}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontSize: 13, fontWeight: 600 }}>{p.title}</div>
                <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>👁 {fmtN(p.views ?? 0)} · ❤️ {p.reactions}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
