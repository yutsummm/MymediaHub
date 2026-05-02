import { store, json } from '../../_store'

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const g = store.groups.find(g => g.id === +id)
  return g ? json(g) : json({ detail: 'Not found' }, 404)
}

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const idx = store.groups.findIndex(g => g.id === +id)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  const data = await req.json()
  store.groups[idx] = { ...store.groups[idx], ...data }
  return json(store.groups[idx])
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const idx = store.groups.findIndex(g => g.id === +id)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  store.groups.splice(idx, 1)
  return json({ ok: true })
}
