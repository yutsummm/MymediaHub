import { store, json } from '../_store'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const start = searchParams.get('start') ?? ''
  const end = searchParams.get('end') ?? ''
  const posts = store.posts.filter(p => {
    const date = p.published_at ?? p.scheduled_at
    if (!date) return false
    return (!start || date >= start) && (!end || date <= end)
  })
  return json(posts)
}
