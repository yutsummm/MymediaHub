import { json } from '../_store'

export async function POST(req: Request) {
  const form = await req.formData()
  const file = form.get('file') as File | null
  if (!file) return json({ detail: 'No file' }, 400)
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  const type = ['jpg','jpeg','png','gif','webp'].includes(ext) ? 'image' : ['mp4','mov','webm'].includes(ext) ? 'video' : 'doc'
  return json({ url: `/uploads/mock-${Date.now()}.${ext}`, type, filename: file.name })
}
