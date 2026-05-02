import { store, json, nextId } from '../_store'

export async function GET() { return json(store.groups) }

export async function POST(req: Request) {
  const { name, description } = await req.json()
  const group = { id: nextId('group'), name, description: description ?? '', avatar: '', role: 'admin' as const, created_by: 1, created_at: new Date().toISOString() }
  store.groups.push(group)
  store.members[group.id] = [{ id: 1, name: 'Анна Королёва', email: 'admin@mediahub.ru', avatar: '', role: 'admin', joined_at: new Date().toISOString() }]
  store.invites[group.id] = []
  return json(group, 201)
}
