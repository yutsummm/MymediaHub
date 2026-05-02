import { store, json } from '../../../../_store'

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string; userId: string }> }) {
  const { id, userId } = await params
  const list = store.members[+id]
  if (!list) return json({ detail: 'Not found' }, 404)
  const idx = list.findIndex(m => m.id === +userId)
  if (idx !== -1) list.splice(idx, 1)
  return json({ ok: true })
}
