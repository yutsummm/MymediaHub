import { store, json } from '../../../_store'

export async function POST() {
  return json(store.groups[0])
}
