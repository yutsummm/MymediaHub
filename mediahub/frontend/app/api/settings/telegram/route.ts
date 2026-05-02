import { json } from '../../_store'

export async function GET() { return json({ connected: false }) }
export async function POST(req: Request) {
  const { chat_id } = await req.json()
  return json({ connected: true, chat_id, chat_title: 'Тестовый Telegram-канал', connected_at: new Date().toISOString() })
}
export async function DELETE() { return json({ connected: false }) }
