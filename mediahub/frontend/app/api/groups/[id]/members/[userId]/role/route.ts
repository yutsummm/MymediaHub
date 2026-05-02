import { store, json } from '../../../../../_store'

export async function PUT(req: Request, { params }: { params: Promise<{ id: string; userId: string }> }) {
  const { id, userId } = await params
  const { role } = await req.json()
  const member = (store.members[+id] ?? []).find(m => m.id === +userId)
  if (!member) return json({ detail: 'Not found' }, 404)
  member.role = role
  return json(member)
}
