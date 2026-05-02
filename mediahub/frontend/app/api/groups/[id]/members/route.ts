import { store, json } from '../../../_store'

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return json(store.members[+id] ?? [])
}
