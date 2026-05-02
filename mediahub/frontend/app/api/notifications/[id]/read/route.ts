import { store, json } from '../../../_store'

export async function PUT(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const n = store.notifications.find(n => n.id === +id)
  if (n) n.is_read = 1
  return json({ ok: true })
}
