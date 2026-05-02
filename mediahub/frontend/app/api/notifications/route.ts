import { store, json } from '../_store'
export async function GET() { return json(store.notifications) }
