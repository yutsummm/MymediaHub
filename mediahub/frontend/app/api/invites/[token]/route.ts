import { json } from '../../_store'

export async function GET() {
  return json({ group_id: 1, group_name: 'Официальный канал', group_description: 'Основная страница', role: 'editor', expires_at: new Date(Date.now() + 86400000).toISOString() })
}
