import { store, json } from '../../../../_store'

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string; linkId: string }> }) {
  const { id, linkId } = await params
  const list = store.invites[+id]
  if (list) { const idx = list.findIndex(l => l.id === +linkId); if (idx !== -1) list.splice(idx, 1) }
  return json({ ok: true })
}
