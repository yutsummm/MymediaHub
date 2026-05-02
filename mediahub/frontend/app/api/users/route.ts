import { store, json, nextId } from '../_store'

export async function GET() { return json(store.users) }

export async function POST(req: Request) {
  const { name, email, role, password: _ } = await req.json()
  const user = { id: nextId('user'), name, email, role, avatar: '', created_at: new Date().toISOString() }
  store.users.push(user)
  return json(user, 201)
}
