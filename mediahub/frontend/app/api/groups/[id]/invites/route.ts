import { store, json, nextId } from '../../../_store'

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return json(store.invites[+id] ?? [])
}

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const { role, expires_hours, max_uses } = await req.json()
  const expires = new Date(Date.now() + (expires_hours ?? 24) * 3600000).toISOString()
  const link = { id: nextId('invite'), token: `mock-${Date.now()}`, role, expires_at: expires, used_count: 0, max_uses: max_uses ?? null, created_at: new Date().toISOString() }
  if (!store.invites[+id]) store.invites[+id] = []
  store.invites[+id].push(link)
  return json(link, 201)
}
