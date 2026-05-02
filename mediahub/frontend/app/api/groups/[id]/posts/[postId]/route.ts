import { store, json } from '../../../../_store'

export async function GET(_: Request, { params }: { params: Promise<{ postId: string }> }) {
  const { postId } = await params
  const post = store.posts.find(p => p.id === +postId)
  return post ? json(post) : json({ detail: 'Not found' }, 404)
}

export async function PUT(req: Request, { params }: { params: Promise<{ postId: string }> }) {
  const { postId } = await params
  const idx = store.posts.findIndex(p => p.id === +postId)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  store.posts[idx] = { ...store.posts[idx], ...await req.json() }
  return json(store.posts[idx])
}

export async function DELETE(_: Request, { params }: { params: Promise<{ postId: string }> }) {
  const { postId } = await params
  const idx = store.posts.findIndex(p => p.id === +postId)
  if (idx !== -1) store.posts.splice(idx, 1)
  return json({ ok: true })
}
