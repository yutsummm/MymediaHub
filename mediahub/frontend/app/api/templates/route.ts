import { templates, json } from '../_store'
export async function GET() { return json(templates) }
