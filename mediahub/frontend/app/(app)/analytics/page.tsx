'use client'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { AnalyticsSummary, TimelinePoint } from '@/lib/types'

declare const Chart: typeof import('chart.js').Chart

const fmtN = (n: number) => n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + 'M' : n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n)

const S18 = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const S14 = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const ANLT_ICONS = [
  <svg key="eye"   {...S18}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  <svg key="heart" {...S18}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>,
  <svg key="msg"   {...S18}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  <svg key="share" {...S18}><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>,
]
const IcoDownload = <svg {...S14}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
const IcoChevron = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>

const MONTHS_RU = ['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь']

function buildMonthOptions() {
  const now = new Date()
  const opts: { label: string; startDate: string; endDate: string }[] = []
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const y = d.getFullYear(), m = d.getMonth()
    const start = `${y}-${String(m + 1).padStart(2, '0')}-01`
    const isCurrentMonth = i === 0
    const lastDay = isCurrentMonth ? now : new Date(y, m + 1, 0)
    const end = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`
    opts.push({ label: `${MONTHS_RU[m]} ${y}${isCurrentMonth ? ' (по сегодня)' : ''}`, startDate: start, endDate: end })
  }
  return opts
}

function useCountUp(target: number, duration = 700): number {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (target === 0) { setVal(0); return }
    let raf: number
    const start = Date.now()
    const tick = () => {
      const p = Math.min((Date.now() - start) / duration, 1)
      setVal(Math.round((1 - (1 - p) ** 3) * target))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return val
}

function genSparkline(seed: number, count = 7): number[] {
  return Array.from({ length: count }, (_, i) => {
    const noise = Math.abs(Math.sin(seed * 3.71 + i * 1.93)) * 0.26
    return Math.min(0.96, Math.max(0.08, 0.14 + (i / (count - 1)) * 0.55 + noise))
  })
}
function Sparkline({ seed }: { seed: number }) {
  const W = 64, H = 24, pts = genSparkline(seed)
  const xs = pts.map((_, i) => (i / (pts.length - 1)) * W)
  const ys = pts.map(v => H - v * H)
  const d = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
  return <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} fill="none" style={{ display: 'block' }}><path d={d} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
}

function StatCard({ label, raw, delta, icon, index }: { label: string; raw: number; delta: string; icon: React.ReactNode; index: number }) {
  const animated = useCountUp(raw)
  return (
    <div className="stat-card anim-in" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="stat-top"><div className="stat-label">{label}</div><div className="stat-icon">{icon}</div></div>
      <div className="stat-value">{fmtN(animated)}</div>
      <div className="stat-delta">↑ {delta} за месяц</div>
      <div className="sparkline-wrap"><Sparkline seed={index * 7.3 + raw * 0.01} /></div>
    </div>
  )
}

function SkeletonStatCard({ index }: { index: number }) {
  return (
    <div className="stat-card anim-in" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="stat-top">
        <div className="skeleton skeleton-text" style={{ width: 80 }}/>
        <div className="skeleton" style={{ width: 18, height: 18, borderRadius: 4 }}/>
      </div>
      <div className="skeleton skeleton-title" style={{ width: 70, marginTop: 14 }}/>
      <div className="skeleton skeleton-text" style={{ width: 100, marginTop: 10 }}/>
    </div>
  )
}

function getChartColors() {
  const style = getComputedStyle(document.documentElement)
  return {
    text3:  style.getPropertyValue('--text-3').trim()  || 'rgba(255,255,255,0.24)',
    border: style.getPropertyValue('--border').trim()  || 'rgba(255,255,255,0.07)',
  }
}

export default function AnalyticsPage() {
  const [sum, setSum] = useState<AnalyticsSummary | null>(null)
  const [tl, setTl] = useState<TimelinePoint[]>([])
  const [period, setPeriod] = useState('month')
  const [exporting, setExporting] = useState(false)
  const monthOptions = buildMonthOptions()
  const [selectedMonth, setSelectedMonth] = useState(0)

  const lineRef = useRef<HTMLCanvasElement>(null)
  const lineChart = useRef<InstanceType<typeof Chart> | null>(null)
  const barRef  = useRef<HTMLCanvasElement>(null)
  const barChart = useRef<InstanceType<typeof Chart> | null>(null)

  useEffect(() => { api.getAnalyticsSummary().then(setSum).catch(console.error) }, [])
  useEffect(() => { api.getTimeline(period).then(setTl).catch(console.error) }, [period])

  useEffect(() => {
    if (!tl.length || !lineRef.current) return
    // @ts-expect-error Chart.js CDN
    if (!window.Chart) return
    lineChart.current?.destroy()
    const { text3, border } = getChartColors()
    // @ts-expect-error Chart.js CDN
    lineChart.current = new window.Chart(lineRef.current.getContext('2d'), {
      type: 'line',
      data: {
        labels: tl.map(d => d.label),
        datasets: [
          { label: 'Просмотры', data: tl.map(d => d.views),     borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,.08)', tension: .4, fill: true, pointRadius: 3, pointHoverRadius: 5 },
          { label: 'Реакции',   data: tl.map(d => d.reactions), borderColor: '#34d399', backgroundColor: 'rgba(52,211,153,.06)', tension: .4, pointRadius: 3, pointHoverRadius: 5 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', labels: { color: text3, font: { size: 12, family: 'Inter, sans-serif' }, usePointStyle: true, pointStyle: 'circle', pointStyleWidth: 8, padding: 20 } } },
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
    // @ts-expect-error Chart.js CDN
    if (!window.Chart) return
    barChart.current?.destroy()
    const d = sum.platform_stats
    const { text3, border } = getChartColors()
    // @ts-expect-error Chart.js CDN
    barChart.current = new window.Chart(barRef.current.getContext('2d'), {
      type: 'bar',
      data: {
        labels: d.map(x => x.platform.toUpperCase()),
        datasets: [
          { label: 'Постов',           data: d.map(x => x.count),                    backgroundColor: 'rgba(124,58,237,0.7)', borderRadius: 5 },
          { label: 'Просмотры (÷100)', data: d.map(x => Math.round(x.views / 100)), backgroundColor: 'rgba(167,139,250,0.7)', borderRadius: 5 },
          { label: 'Реакции',          data: d.map(x => x.reactions),                backgroundColor: 'rgba(52,211,153,0.7)', borderRadius: 5 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { color: text3, font: { size: 12, family: 'Inter, sans-serif' }, usePointStyle: true, pointStyle: 'circle', pointStyleWidth: 8, padding: 20 } } },
        scales: {
          y: { ticks: { color: text3, font: { size: 11 } }, grid: { color: border } },
          x: { ticks: { color: text3, font: { size: 11 } }, grid: { color: border } },
        },
      },
    })
    return () => { barChart.current?.destroy() }
  }, [sum])

  async function handleExport() {
    const opt = monthOptions[selectedMonth]
    setExporting(true)
    try { await api.exportAnalytics(opt.startDate, opt.endDate) }
    catch (e) { alert((e as Error).message) }
    finally { setExporting(false) }
  }

  const mc = sum ? [
    { label: 'Просмотров',   raw: sum.total_views,     delta: '+18%', icon: ANLT_ICONS[0] },
    { label: 'Реакций',      raw: sum.total_reactions, delta: '+9%',  icon: ANLT_ICONS[1] },
    { label: 'Комментариев', raw: sum.total_comments,  delta: '+12%', icon: ANLT_ICONS[2] },
    { label: 'Репостов',     raw: sum.total_shares,    delta: '+7%',  icon: ANLT_ICONS[3] },
  ] : []

  return (
    <div className="content">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" async />

      {/* Stat cards */}
      <div className="grid4" style={{ marginBottom: 20 }}>
        {sum
          ? mc.map((c, i) => <StatCard key={i} index={i} label={c.label} raw={c.raw} delta={c.delta} icon={c.icon} />)
          : [0,1,2,3].map(i => <SkeletonStatCard key={i} index={i} />)
        }
      </div>

      {/* Timeline chart */}
      <div className="card mb6 anim-in" style={{ animationDelay: '200ms' }}>
        <div className="card-header">
          <span className="card-title">Динамика охватов</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <div className="period-seg">
              {(['week', 'month', 'quarter'] as const).map(p => (
                <button key={p} className={`period-seg-btn${period === p ? ' active' : ''}`} onClick={() => setPeriod(p)}>
                  {{ week: 'Неделя', month: 'Месяц', quarter: 'Квартал' }[p]}
                </button>
              ))}
            </div>
            <div style={{ width: 1, height: 20, background: 'var(--border)', flexShrink: 0 }} />
            <select className="fsel" value={selectedMonth} onChange={e => setSelectedMonth(Number(e.target.value))} style={{ fontSize: 12, padding: '5px 10px', borderRadius: 'var(--r-full)' }}>
              {monthOptions.map((o, i) => <option key={i} value={i}>{o.label}</option>)}
            </select>
            <button className="btn btn-sm btn-secondary" onClick={handleExport} disabled={exporting} style={{ gap: 5 }}>
              {exporting ? <div className="ai-spinner" style={{ width: 13, height: 13 }} /> : IcoDownload}
              {exporting ? 'Формируем...' : 'Excel'}
            </button>
          </div>
        </div>
        <div style={{ padding: '4px 20px 20px' }}>
          <div className="chart-box"><canvas ref={lineRef} /></div>
        </div>
      </div>

      {/* Bottom grid */}
      <div className="grid2">
        <div className="card anim-in" style={{ animationDelay: '260ms' }}>
          <div className="card-header"><span className="card-title">Сравнение площадок</span></div>
          <div style={{ padding: 20 }}>
            <div className="chart-box" style={{ height: 200 }}><canvas ref={barRef} /></div>
          </div>
        </div>

        <div className="card anim-in" style={{ animationDelay: '300ms' }}>
          <div className="card-header"><span className="card-title">Топ-5 постов</span></div>
          {!sum ? (
            [0,1,2,3,4].map(i => (
              <div key={i} style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12, alignItems: 'center' }}>
                <div className="skeleton" style={{ width: 26, height: 26, borderRadius: 6, flexShrink: 0 }}/>
                <div style={{ flex: 1 }}>
                  <div className="skeleton skeleton-text" style={{ width: '75%', marginBottom: 6 }}/>
                  <div className="skeleton skeleton-text" style={{ width: '45%' }}/>
                </div>
              </div>
            ))
          ) : sum.top_posts.length === 0 ? (
            <div style={{ padding: '28px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12, lineHeight: 1.7 }}>
              Данные появятся после первых публикаций
            </div>
          ) : sum.top_posts.map((p, i) => (
            <div key={p.id} style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', transition: 'background var(--dur-fast) var(--ease-out)' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-h)')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              <div style={{ width: 26, height: 26, borderRadius: 6, flexShrink: 0, background: i === 0 ? 'var(--accent)' : 'var(--surface-2)', color: i === 0 ? 'var(--btn-primary-fg)' : 'var(--text-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800 }}>
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="trunc" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>{p.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{fmtN(p.views ?? 0)} просм · {p.reactions} реакций</div>
              </div>
              <span style={{ color: 'var(--text-3)', opacity: 0.4, flexShrink: 0 }}>{IcoChevron}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
