'use client'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { AnalyticsSummary, TimelinePoint } from '@/lib/types'

declare const Chart: typeof import('chart.js').Chart

const fmtN = (n: number) => n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)

/* ── SVG props ── */
const S18 = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const S14 = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const ANLT_ICONS = [
  <svg key="eye"   {...S18}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  <svg key="heart" {...S18}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>,
  <svg key="msg"   {...S18}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  <svg key="share" {...S18}><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>,
]

const IcoDownload = <svg {...S14}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
const IcoLoader   = <svg {...S14}><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>

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
    const lastDay = isCurrentMonth ? now : new Date(y, m + 1, 0)
    const end = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`
    opts.push({ label: `${MONTHS_RU[m]} ${y}${isCurrentMonth ? ' (по сегодня)' : ''}`, startDate: start, endDate: end })
  }
  return opts
}

/* ── Animated counter (ease-out cubic) ── */
function useCountUp(target: number, duration = 720): number {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (target === 0) { setVal(0); return }
    let raf: number
    const start = Date.now()
    const tick = () => {
      const p     = Math.min((Date.now() - start) / duration, 1)
      const eased = 1 - (1 - p) ** 3
      setVal(Math.round(eased * target))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return val
}

/* ── Deterministic sparkline ── */
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

/* ── Stat card ── */
function StatCard({ label, raw, delta, icon, index }: {
  label: string; raw: number; delta: string; icon: React.ReactNode; index: number
}) {
  const animated = useCountUp(raw)
  return (
    <div className="stat-card anim-in" style={{ animationDelay: `${index * 40}ms` }}>
      <div className="stat-top">
        <div className="stat-label">{label}</div>
        <div className="stat-icon">{icon}</div>
      </div>
      <div className="stat-value">{fmtN(animated)}</div>
      <div className="stat-delta">↑ {delta} за месяц</div>
      <div className="sparkline-wrap">
        <Sparkline seed={index * 7.3 + raw * 0.01} />
      </div>
    </div>
  )
}

/* ── Theme-aware chart colors ── */
function getChartColors() {
  const style = getComputedStyle(document.documentElement)
  const text3 = style.getPropertyValue('--text-3').trim() || 'rgba(255,255,255,0.26)'
  const border = style.getPropertyValue('--border').trim() || 'rgba(255,255,255,0.08)'
  return { text3, border }
}

export default function AnalyticsPage() {
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [tl, setTl]   = useState<TimelinePoint[]>([])
  const [period, setPeriod]   = useState('month')
  const [exporting, setExporting] = useState(false)
  const monthOptions   = buildMonthOptions()
  const [selectedMonth, setSelectedMonth] = useState(0)

  async function handleExport() {
    const opt = monthOptions[selectedMonth]
    setExporting(true)
    try { await api.exportAnalytics(opt.startDate, opt.endDate) }
    catch (e) { alert((e as Error).message) }
    finally { setExporting(false) }
  }

  const lineRef   = useRef<HTMLCanvasElement>(null)
  const lineChart = useRef<InstanceType<typeof Chart> | null>(null)
  const barRef    = useRef<HTMLCanvasElement>(null)
  const barChart  = useRef<InstanceType<typeof Chart> | null>(null)

  useEffect(() => { api.getAnalyticsSummary().then(setSum).catch(console.error) }, [])
  useEffect(() => { api.getTimeline(period).then(setTl).catch(console.error) }, [period])

  useEffect(() => {
    if (!tl.length || !lineRef.current) return
    // @ts-expect-error Chart.js loaded via CDN
    if (!window.Chart) return
    lineChart.current?.destroy()
    const { text3, border } = getChartColors()
    // @ts-expect-error Chart.js loaded via CDN
    lineChart.current = new window.Chart(lineRef.current.getContext('2d'), {
      type: 'line',
      data: {
        labels: tl.map(d => d.label),
        datasets: [
          { label: 'Просмотры', data: tl.map(d => d.views),     borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,.1)', tension: .4, fill: true, pointRadius: 3, pointHoverRadius: 5 },
          { label: 'Реакции',   data: tl.map(d => d.reactions), borderColor: '#34d399', backgroundColor: 'rgba(52,211,153,.08)', tension: .4, pointRadius: 3, pointHoverRadius: 5 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', labels: { color: text3, font: { size: 12, family: 'Inter, sans-serif' }, boxWidth: 12, padding: 16 } } },
        scales: {
          y: { beginAtZero: true, ticks: { color: text3, font: { size: 11 } }, grid: { color: border } },
          x: { ticks: { color: text3, font: { size: 11 } }, grid: { color: border } },
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
    const { text3, border } = getChartColors()
    // @ts-expect-error Chart.js loaded via CDN
    barChart.current = new window.Chart(barRef.current.getContext('2d'), {
      type: 'bar',
      data: {
        labels: d.map(x => x.platform.toUpperCase()),
        datasets: [
          { label: 'Постов',           data: d.map(x => x.count),                    backgroundColor: '#7c3aed', borderRadius: 4 },
          { label: 'Просмотры (÷100)', data: d.map(x => Math.round(x.views / 100)), backgroundColor: '#a78bfa', borderRadius: 4 },
          { label: 'Реакции',          data: d.map(x => x.reactions),                backgroundColor: '#34d399', borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { color: text3, font: { size: 12, family: 'Inter, sans-serif' }, boxWidth: 12, padding: 16 } } },
        scales: {
          y: { ticks: { color: text3, font: { size: 11 } }, grid: { color: border } },
          x: { ticks: { color: text3, font: { size: 11 } }, grid: { color: border } },
        },
      },
    })
    return () => { barChart.current?.destroy() }
  }, [sum])

  if (!sum) return (
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

  const mc = [
    { label: 'Просмотров',   raw: sum.total_views,     delta: '+18%', icon: ANLT_ICONS[0] },
    { label: 'Реакций',      raw: sum.total_reactions, delta: '+9%',  icon: ANLT_ICONS[1] },
    { label: 'Комментариев', raw: sum.total_comments,  delta: '+12%', icon: ANLT_ICONS[2] },
    { label: 'Репостов',     raw: sum.total_shares,    delta: '+7%',  icon: ANLT_ICONS[3] },
  ]

  return (
    <div className="content">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" async />

      {/* ── Stat cards ── */}
      <div className="grid4" style={{ marginBottom: 20 }}>
        {mc.map((c, i) => (
          <StatCard key={i} index={i} label={c.label} raw={c.raw} delta={c.delta} icon={c.icon} />
        ))}
      </div>

      {/* ── Timeline chart ── */}
      <div className="card mb6">
        <div className="card-header">
          <span className="card-title">Динамика охватов</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div className="period-seg">
              {(['week', 'month', 'quarter'] as const).map(p => (
                <button
                  key={p}
                  className={`period-seg-btn${period === p ? ' active' : ''}`}
                  onClick={() => setPeriod(p)}
                >
                  {{ week: 'Неделя', month: 'Месяц', quarter: 'Квартал' }[p]}
                </button>
              ))}
            </div>
            <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 2px' }} />
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
              style={{ gap: 5 }}
            >
              {exporting ? IcoLoader : IcoDownload}
              {exporting ? 'Формируем...' : 'Excel'}
            </button>
          </div>
        </div>
        <div style={{ padding: '4px 20px 20px' }}>
          <div className="chart-box"><canvas ref={lineRef} /></div>
        </div>
      </div>

      {/* ── Bottom grid ── */}
      <div className="grid2">
        <div className="card">
          <div className="card-header"><span className="card-title">Сравнение площадок</span></div>
          <div style={{ padding: 20 }}>
            <div className="chart-box" style={{ height: 200 }}><canvas ref={barRef} /></div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Топ-5 постов</span></div>
          {sum.top_posts.length === 0 ? (
            <div style={{ padding: '24px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
              Данные появятся после первых публикаций
            </div>
          ) : sum.top_posts.map((p, i) => (
            <div
              key={p.id}
              style={{
                padding: '12px 20px',
                borderBottom: '1px solid var(--border)',
                display: 'flex', gap: 12, alignItems: 'center',
                cursor: 'pointer',
                transition: 'background 0.15s var(--ease-out)',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-h)')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              <div style={{
                width: 26, height: 26, borderRadius: 6, flexShrink: 0,
                background: i === 0 ? 'var(--accent)' : 'var(--surface-2)',
                color: i === 0 ? 'var(--btn-primary-fg)' : 'var(--text-3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 800,
                transition: 'background 0.15s var(--ease-out)',
              }}>{i + 1}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>{p.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{fmtN(p.views ?? 0)} просм · {p.reactions} реакций</div>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--text-3)', flexShrink: 0, opacity: 0.5 }}>
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
