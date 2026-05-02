import { store, json, nextId } from '../_store'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const status = searchParams.get('status')
  const platform = searchParams.get('platform')
  const search = searchParams.get('search')?.toLowerCase()
  const page = parseInt(searchParams.get('page') ?? '1')
  const limit = parseInt(searchParams.get('limit') ?? '20')

  let posts = [...store.posts].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  if (status) posts = posts.filter(p => p.status === status)
  if (platform) posts = posts.filter(p => p.platforms.includes(platform))
  if (search) posts = posts.filter(p => p.title.toLowerCase().includes(search) || p.content.toLowerCase().includes(search))

  const total = posts.length
  const offset = (page - 1) * limit
  return json({ posts: posts.slice(offset, offset + limit), total })
}

export async function POST(req: Request) {
  const data = await req.json()
  const post = {
    id: nextId('post'),
    author_id: 1, author_name: 'Анна Королёва',
    views: 0, reactions: 0, comments: 0, shares: 0,
    media: [], created_at: new Date().toISOString(),
    ...data,
    published_at: data.status === 'published' ? new Date().toISOString() : null,
  }
  store.posts.unshift(post)
  return json(post, 201)
}
