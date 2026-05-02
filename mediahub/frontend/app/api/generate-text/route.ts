import { json } from '../_store'

const stubs: Record<string, (f: Record<string, string>) => { title: string; text: string }> = {
  announcement: f => ({
    title: f.event_name ?? 'Мероприятие',
    text: `📢 Приглашаем вас на ${f.event_name ?? 'мероприятие'}!\n\n📅 Дата: ${f.date ?? 'уточняется'}\n📍 Место: ${f.location ?? 'уточняется'}\n\n${f.description ?? ''}\n\nНе пропустите — регистрация уже открыта! Ссылка в описании.`,
  }),
  results: f => ({
    title: `Итоги: ${f.event_name ?? 'мероприятие'}`,
    text: `✅ Подведены итоги ${f.event_name ?? 'события'}!\n\n📊 Ключевые результаты:\n${f.key_results ?? ''}\n\n🏆 ${f.winner ?? 'Победитель определён'}\n\nСпасибо всем участникам — до встречи на следующем мероприятии!`,
  }),
  vacancy: f => ({
    title: `Вакансия: ${f.position ?? 'специалист'}`,
    text: `💼 Открыта вакансия: ${f.position ?? 'специалист'}\n\n📋 Требования:\n${f.requirements ?? ''}\n\n💰 Условия:\n${f.conditions ?? ''}\n\n📩 Откликнуться: ${f.contacts ?? 'пишите нам'}`,
  }),
  grant: f => ({
    title: f.grant_name ?? 'Конкурс грантов',
    text: `🎯 Объявлен ${f.grant_name ?? 'конкурс грантов'}!\n\n💰 Размер финансирования: ${f.amount ?? 'уточняется'}\n📅 Дедлайн: ${f.deadline ?? 'уточняется'}\n\n👥 Требования к участникам:\n${f.requirements ?? ''}\n\nПодайте заявку и реализуйте свой проект! 🚀`,
  }),
}

export async function POST(req: Request) {
  const { template_type, fields } = await req.json()
  const gen = stubs[template_type]
  if (!gen) return json({ detail: 'Unknown template' }, 400)
  const { title, text } = gen(fields ?? {})
  return json({ title, text })
}
