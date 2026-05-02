import { json } from '../../_store'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const period = searchParams.get('period') ?? 'week'
  const points = period === 'week' ? 7 : period === 'month' ? 30 : 12
  const now = Date.now()

  const timeline = Array.from({ length: points }, (_, i) => {
    const date = new Date(now - (points - 1 - i) * (period === 'year' ? 30 : 1) * 86400000)
    const label = period === 'year'
      ? date.toLocaleString('ru', { month: 'short' })
      : date.toLocaleString('ru', { day: 'numeric', month: 'short' })
    const base = 800 + Math.sin(i * 0.8) * 300
    return {
      date: date.toISOString().slice(0, 10),
      label,
      views: Math.round(base + Math.random() * 400),
      reactions: Math.round(base * 0.08 + Math.random() * 30),
      posts: Math.floor(Math.random() * 3),
    }
  })
  return json(timeline)
}
