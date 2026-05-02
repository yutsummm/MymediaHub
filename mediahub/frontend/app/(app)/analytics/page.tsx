'use client'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { AnalyticsSummary, TimelinePoint } from '@/lib/types'

declare const Chart: typeof import('chart.js').Chart

const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)

const S = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const ANLT_ICONS = [
  <svg key="eye"     {...S}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  <svg key="heart"   {...S}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>,
  <svg key="msg"     {...S}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  <svg key="share"   {...S}><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>,
]

const MONTHS_RU = ['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь']

function buildMonthOptions() {
  const now = new Date()
  const opts: { label: string; startDate: string; endDate: string }[] = []
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const y = d.getFullYear()
    const m = d.getMonth()
    const start = `${y}-${String(m + 1).padStart(2, '0')}-01`
    const isCurrentMonth = i === 0
    const lastDay = isCurrentMonth
      ? now
      : new Date(y, m + 1, 0)
    const end = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`
    const suffix = isCurrentMonth ? ' (по сегодня)' : ''
    opts.push({ label: `${MONTHS_RU[m]} ${y}${suffix}`, startDate: start, endDate: end })
  }
  return opts
}

export default function AnalyticsPage() {
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [tl, setTl] = useState<TimelinePoint[]>([])
  const [period, setPeriod] = useState('month')
  const [exporting, setExporting] = useState(false)
  const monthOptions = buildMonthOptions()
  const [selectedMonth, setSelectedMonth] = useState(0)

  async function handleExport() {
    const opt = monthOptions[selectedMonth]
    setExporting(true)
    try { await api.exportAnalytics(opt.startDate, opt.endDate) } catch (e) { alert((e as Error).message) } finally { setExporting(false) }
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
    { label: 'Просмотров',   val: fmtN(sum.total_views)     },
    { label: 'Реакций',      val: fmtN(sum.total_reactions) },
    { label: 'Комментариев', val: fmtN(sum.total_comments)  },
    { label: 'Репостов',     val: fmtN(sum.total_shares)    },
  ]

  return (
    <div className="content">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" async />

      <div className="grid4" style={{ marginBottom: 20 }}>
        {mc.map((c, i) => (
          <div key={i} className="stat-card anim-in">
            <div className="stat-head">
              <div className="stat-label">{c.label}</div>
              <div className="stat-ico">{ANLT_ICONS[i]}</div>
            </div>
            <div className="stat-value">{c.val}</div>
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
            <select
              className="fsel"
              value={selectedMonth}
              onChange={e => setSelectedMonth(Number(e.target.value))}
              style={{ fontSize: 12, padding: '5px 10px', borderRadius: 'var(--r-full)' }}
            >
              {monthOptions.map((o, i) => (
                <option key={i} value={i}>{o.label}</option>
              ))}
            </select>
            <button
              className="btn btn-sm btn-secondary"
              onClick={handleExport}
              disabled={exporting}
              title="Скачать отчёт в Excel"
            >
              {exporting ? '⏳ Формируем...' : '⬇ Excel'}
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
                background: i === 0 ? 'var(--accent)' : 'var(--surface-2)',
                color: i === 0 ? 'var(--btn-primary-fg)' : 'var(--text-3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
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
