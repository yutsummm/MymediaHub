import { json } from '../../../../_store'

export async function GET() { return json({ connected: false }) }
export async function POST(req: Request) {
  const { group_id } = await req.json()
  return json({ connected: true, group_id, group_name: 'Тестовая группа ВК', connected_at: new Date().toISOString() })
}
export async function DELETE() { return json({ connected: false }) }
