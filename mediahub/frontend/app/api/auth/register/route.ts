import { store, json, nextId } from '../../_store'

export async function POST(req: Request) {
  const { name, email } = await req.json()
  const user = { id: nextId('user'), name, email, role: 'editor' as const, avatar: '', created_at: new Date().toISOString() }
  store.users.push(user)
  return json({ user, token: 'mock-token-local-dev' })
}
