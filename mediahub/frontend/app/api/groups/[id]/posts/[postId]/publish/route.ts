import { store, json } from '../../../../../_store'

export async function POST(_: Request, { params }: { params: Promise<{ postId: string }> }) {
  const { postId } = await params
  const idx = store.posts.findIndex(p => p.id === +postId)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  store.posts[idx] = { ...store.posts[idx], status: 'published', published_at: new Date().toISOString() }
  return json(store.posts[idx])
}
