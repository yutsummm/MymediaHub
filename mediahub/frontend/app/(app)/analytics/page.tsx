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
  const [exporting, setExporting] = useState(false)

  async function handleExport() {
    setExporting(true)
    try { await api.exportAnalytics(period) } catch (e) { alert((e as Error).message) } finally { setExporting(false) }
  }
  const lineRef  = useRef<HTMLCanvasElement>(null)
  const lineChart = useRef<InstanceType<typeof Chart> | null>(null)
  const barRef   = useRef<HTMLCanvasElement>(null)
  const barChart  = useRef<InstanceType<typeof Chart> | null>(null)

  useEffect(() => { api.getAnalyticsSummary().then(setSum).catch(console.error) }, [])
  useEffect(() => { api.getTimeline(period).then(setTl).catch(console.error) }, [period])

  useEffect(() => {
    if (!tl.length || !lineRef.current) return
    // @ts-expect-error Chart.js loaded via CDN
    if (!window.Chart) return
    lineChart.current?.destroy()
    // @ts-expect-error Chart.js loaded via CDN
    lineChart.current = new window.Chart(lineRef.current.getContext('2d'), {
      type: 'line',
      data: {
        labels: tl.map(d => d.label),
        datasets: [
          { label: 'Просмотры', data: tl.map(d => d.views),     borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,.1)', tension: .4, fill: true },
          { label: 'Реакции',   data: tl.map(d => d.reactions), borderColor: '#34d399', backgroundColor: 'rgba(52,211,153,.08)', tension: .4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { color: 'rgba(255,255,255,0.52)', font: { size: 12 } } } },
        scales: {
          y: { beginAtZero: true, ticks: { color: 'rgba(255,255,255,0.24)' }, grid: { color: 'rgba(255,255,255,0.06)' } },
          x: { ticks: { color: 'rgba(255,255,255,0.24)' }, grid: { color: 'rgba(255,255,255,0.06)' } },
        },
      },
    })
    return () => { lineChart.current?.destroy() }
  }, [tl])

  useEffect(() => {
    if (!sum?.platform_stats || !barRef.current) return
    // @ts-expect-error Chart.js loaded via CDN
    if (!window.Chart) return
    barChart.current?.destroy()
    const d = sum.platform_stats
    // @ts-expect-error Chart.js loaded via CDN
    barChart.current = new window.Chart(barRef.current.getContext('2d'), {
      type: 'bar',
      data: {
        labels: d.map(x => x.platform.toUpperCase()),
        datasets: [
          { label: 'Постов',           data: d.map(x => x.count),                    backgroundColor: '#7c3aed' },
          { label: 'Просмотры (÷100)', data: d.map(x => Math.round(x.views / 100)), backgroundColor: '#a78bfa' },
          { label: 'Реакции',          data: d.map(x => x.reactions),                backgroundColor: '#34d399' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { color: 'rgba(255,255,255,0.52)', font: { size: 12 } } } },
        scales: {
          y: { ticks: { color: 'rgba(255,255,255,0.24)' }, grid: { color: 'rgba(255,255,255,0.06)' } },
          x: { ticks: { color: 'rgba(255,255,255,0.24)' }, grid: { color: 'rgba(255,255,255,0.06)' } },
        },
      },
    })
    return () => { barChart.current?.destroy() }
  }, [sum])

  if (!sum) return (
    <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-3)' }}>
        <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.4 }}>↗</div>
        <div style={{ fontSize: 13, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600 }}>Загрузка</div>
      </div>
    </div>
  )

  const mc = [
    { label: 'Просмотров',    val: fmtN(sum.total_views),     color: '#60a5fa', bg: 'rgba(59,130,246,0.12)' },
    { label: 'Реакций',       val: fmtN(sum.total_reactions), color: '#f87171', bg: 'rgba(239,68,68,0.12)' },
    { label: 'Комментариев',  val: fmtN(sum.total_comments),  color: '#34d399', bg: 'rgba(16,185,129,0.12)' },
    { label: 'Репостов',      val: fmtN(sum.total_shares),    color: '#fbbf24', bg: 'rgba(245,158,11,0.12)' },
  ]

  return (
    <div className="content">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" async />

      <div className="grid4" style={{ marginBottom: 20 }}>
        {mc.map((c, i) => (
          <div key={i} className="stat-card anim-in">
            <div className="stat-icon" style={{ background: c.bg }}>
              <span style={{ color: c.color, fontSize: 15, fontWeight: 800 }}>
                {i === 0 ? '↗' : i === 1 ? '♥' : i === 2 ? '◉' : '⇌'}
              </span>
            </div>
            <div className="stat-value" style={{ color: c.color }}>{c.val}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="card mb6">
        <div className="card-header">
          <span className="card-title">Динамика охватов</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {(['week', 'month', 'quarter'] as const).map(p => (
              <button key={p} className={`btn btn-sm ${period === p ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setPeriod(p)}>
                {{ week: 'Неделя', month: 'Месяц', quarter: 'Квартал' }[p]}
              </button>
            ))}
            <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />
            <button
              className="btn btn-sm btn-secondary"
              onClick={handleExport}
              disabled={exporting}
              title="Скачать отчёт в Excel"
              style={{ gap: 5 }}
            >
              {exporting ? '⏳' : '⬇'} {exporting ? 'Формируем...' : 'Excel'}
            </button>
          </div>
        </div>
        <div style={{ padding: 20 }}>
          <div className="chart-box"><canvas ref={lineRef} /></div>
        </div>
      </div>

      <div className="grid2">
        <div className="card">
          <div className="card-header"><span className="card-title">Сравнение площадок</span></div>
          <div style={{ padding: 20 }}>
            <div className="chart-box" style={{ height: 200 }}><canvas ref={barRef} /></div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Топ-5 постов</span></div>
          {sum.top_posts.map((p, i) => (
            <div key={p.id} style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{
                width: 26, height: 26, borderRadius: 6,
                background: ['linear-gradient(135deg,#f59e0b,#fbbf24)', 'linear-gradient(135deg,#6b7280,#9ca3af)', 'linear-gradient(135deg,#92400e,#b45309)', 'var(--surface-2)', 'var(--surface-2)'][i],
                color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 800, flexShrink: 0,
              }}>{i + 1}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{p.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{fmtN(p.views ?? 0)} просм · {p.reactions} реакций</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
