import { json } from '../_store'

function creative(text: string): string {
  const emojis = ['🚀', '🎯', '💡', '✨', '🔥', '💪', '🌟', '👇', '📢', '🎉']
  const pick = () => emojis[Math.floor(Math.random() * emojis.length)]
  const lines = text.split('\n').filter(Boolean)
  const enhanced = lines.map((line, i) => {
    if (i === 0) return `${pick()} ${line}`
    if (line.length > 40 && Math.random() > 0.5) return `${line} ${pick()}`
    return line
  })
  enhanced.push('', `👇 Подписывайтесь, чтобы не пропускать важные новости!`)
  return enhanced.join('\n')
}

function russify(text: string): string {
  const map: Record<string, string> = {
    'контент': 'содержимое', 'пост': 'публикация', 'дедлайн': 'срок', 'митинг': 'собрание',
    'фидбек': 'отклик', 'апдейт': 'обновление', 'чекин': 'отметка', 'скоп': 'охват',
    'лайк': 'отметка «нравится»', 'шер': 'репост', 'бекенд': 'серверная часть',
    'фронтенд': 'клиентская часть', 'релиз': 'выпуск', 'фиче': 'функция',
  }
  let result = text
  for (const [en, ru] of Object.entries(map)) {
    result = result.replace(new RegExp(en, 'gi'), ru)
  }
  return result
}

export async function POST(req: Request) {
  const { text, mode } = await req.json()
  if (!text?.trim()) return json({ detail: 'Empty text' }, 400)
  const enhanced = mode === 'russify' ? russify(text) : creative(text)
  return json({ text: enhanced })
}
