import { store, json, nextId } from '../../../_store'

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const { searchParams } = new URL(req.url)
  const status = searchParams.get('status')
  let posts = store.posts.filter(p => !status || p.status === status)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  const page = parseInt(searchParams.get('page') ?? '1')
  const limit = parseInt(searchParams.get('limit') ?? '20')
  return json({ posts: posts.slice((page - 1) * limit, page * limit), total: posts.length })
}

export async function POST(req: Request) {
  const data = await req.json()
  const post = { id: nextId('post'), author_id: 1, author_name: 'Анна Королёва', views: 0, reactions: 0, comments: 0, shares: 0, media: [], created_at: new Date().toISOString(), published_at: data.status === 'published' ? new Date().toISOString() : null, ...data }
  store.posts.unshift(post)
  return json(post, 201)
}
