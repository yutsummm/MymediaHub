import { store, json } from '../../_store'

function find(id: number) { return store.posts.findIndex(p => p.id === id) }

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const post = store.posts.find(p => p.id === +id)
  return post ? json(post) : json({ detail: 'Not found' }, 404)
}

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const idx = find(+id)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  const data = await req.json()
  store.posts[idx] = { ...store.posts[idx], ...data }
  return json(store.posts[idx])
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const idx = find(+id)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  store.posts.splice(idx, 1)
  return json({ ok: true })
}
