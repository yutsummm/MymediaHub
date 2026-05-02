import { store, json } from '../../../_store'

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const { role } = await req.json()
  const user = store.users.find(u => u.id === +id)
  if (!user) return json({ detail: 'Not found' }, 404)
  user.role = role
  return json(user)
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const idx = store.users.findIndex(u => u.id === +id)
  if (idx === -1) return json({ detail: 'Not found' }, 404)
  store.users.splice(idx, 1)
  return json({ ok: true })
}
