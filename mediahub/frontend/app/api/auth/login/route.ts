import { store, json } from '../../_store'

export async function POST(req: Request) {
  const { email } = await req.json()
  const user = store.users.find(u => u.email === email) ?? store.users[0]
  return json({ user, token: 'mock-token-local-dev' })
}
