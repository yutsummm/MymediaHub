import type { Post, User, Notification, Group, GroupMember, InviteLink, Template } from '@/lib/types'

interface Store {
  users: User[]
  posts: Post[]
  notifications: Notification[]
  groups: Group[]
  members: Record<number, GroupMember[]>
  invites: Record<number, InviteLink[]>
  nextId: Record<string, number>
}

function init(): Store {
  const now = new Date()
  const d = (days: number) => new Date(now.getTime() + days * 86400000).toISOString()

  const users: User[] = [
    { id: 1, name: 'Анна Королёва', email: 'admin@mediahub.ru', role: 'admin', avatar: '', created_at: d(-30) },
    { id: 2, name: 'Дмитрий Волков', email: 'editor@mediahub.ru', role: 'editor', avatar: '', created_at: d(-20) },
    { id: 3, name: 'Светлана Михайлова', email: 'observer@mediahub.ru', role: 'observer', avatar: '', created_at: d(-10) },
  ]

  const posts: Post[] = [
    {
      id: 1, title: 'Открытый конкурс грантов 2026', author_id: 1, author_name: 'Анна Королёва',
      content: 'Уважаемые участники! Объявляем о старте конкурса грантов на развитие молодёжных проектов. Подача заявок до 30 мая 2026 года. Максимальный размер гранта — 500 000 ₽. Не упустите возможность реализовать свою идею! 🎯',
      status: 'published', platforms: ['vk', 'telegram'], tags: ['гранты', 'молодёжь'],
      scheduled_at: null, published_at: d(-5),
      views: 4821, reactions: 312, comments: 47, shares: 89,
      template_type: 'grant', created_at: d(-6), media: [], location_address: null, location_lat: null, location_lng: null,
    },
    {
      id: 2, title: 'Весенний хакатон «Цифровой регион»', author_id: 2, author_name: 'Дмитрий Волков',
      content: '💻 Приглашаем разработчиков, дизайнеров и менеджеров принять участие в хакатоне! 48 часов интенсивной работы, крутые задачи от региональных партнёров, призовой фонд 1 000 000 ₽. Регистрация открыта на сайте.',
      status: 'published', platforms: ['vk'], tags: ['мероприятия', 'IT'],
      scheduled_at: null, published_at: d(-3),
      views: 2104, reactions: 187, comments: 32, shares: 54,
      template_type: 'announcement', created_at: d(-4), media: [], location_address: 'Москва, Технопарк «Сколково»', location_lat: 55.695, location_lng: 37.357,
    },
    {
      id: 3, title: 'Вакансия: SMM-специалист', author_id: 1, author_name: 'Анна Королёва',
      content: 'Мы ищем опытного SMM-специалиста в нашу команду. Требования: опыт от 2 лет, знание VK/Telegram, умение работать с аналитикой. Условия: удалённый формат, зарплата от 60 000 ₽. Резюме на hr@mediahub.ru',
      status: 'published', platforms: ['telegram'], tags: ['вакансии'],
      scheduled_at: null, published_at: d(-2),
      views: 1560, reactions: 94, comments: 18, shares: 41,
      template_type: 'vacancy', created_at: d(-3), media: [], location_address: null, location_lat: null, location_lng: null,
    },
    {
      id: 4, title: 'Итоги I квартала 2026', author_id: 1, author_name: 'Анна Королёва',
      content: 'Подводим итоги первого квартала: опубликовано 47 постов, охват аудитории вырос на 34%, количество подписчиков увеличилось до 28 000. Спасибо всей команде за отличную работу! 📈',
      status: 'scheduled', platforms: ['vk', 'telegram'], tags: ['новости'],
      scheduled_at: d(2), published_at: null,
      views: 0, reactions: 0, comments: 0, shares: 0,
      template_type: 'results', created_at: d(-1), media: [], location_address: null, location_lat: null, location_lng: null,
    },
    {
      id: 5, title: 'День открытых дверей — май 2026', author_id: 2, author_name: 'Дмитрий Волков',
      content: 'Приглашаем всех желающих на день открытых дверей! Вы сможете познакомиться с нашими проектами, пообщаться с командой и узнать о возможностях для сотрудничества. Вход свободный.',
      status: 'scheduled', platforms: ['vk'], tags: ['мероприятия'],
      scheduled_at: d(7), published_at: null,
      views: 0, reactions: 0, comments: 0, shares: 0,
      template_type: 'announcement', created_at: d(0), media: [], location_address: 'Санкт-Петербург, пр. Невский, 1', location_lat: 59.936, location_lng: 30.325,
    },
    {
      id: 6, title: 'Черновик: Конференция по цифровизации', author_id: 2, author_name: 'Дмитрий Волков',
      content: 'В июне пройдёт ежегодная конференция по цифровизации государственного управления. Основные темы: электронные сервисы, большие данные, кибербезопасность.',
      status: 'draft', platforms: ['vk', 'telegram'], tags: ['мероприятия', 'новости'],
      scheduled_at: null, published_at: null,
      views: 0, reactions: 0, comments: 0, shares: 0,
      template_type: null, created_at: d(0), media: [], location_address: null, location_lat: null, location_lng: null,
    },
    {
      id: 7, title: 'Грант на поддержку стартапов', author_id: 1, author_name: 'Анна Королёва',
      content: '🚀 Стартовал приём заявок на получение гранта для технологических стартапов. Финансирование до 2 000 000 ₽. Приоритетные направления: ИИ, медтех, агротех, экология.',
      status: 'published', platforms: ['vk', 'telegram'], tags: ['гранты'],
      scheduled_at: null, published_at: d(-8),
      views: 6340, reactions: 520, comments: 73, shares: 145,
      template_type: 'grant', created_at: d(-9), media: [], location_address: null, location_lat: null, location_lng: null,
    },
    {
      id: 8, title: 'Новые вакансии в цифровом блоке', author_id: 2, author_name: 'Дмитрий Волков',
      content: 'Открыты новые вакансии: Python-разработчик, UX-дизайнер, аналитик данных. Работа в молодой команде, современный стек, гибкий график. Подробности на карьерном портале.',
      status: 'published', platforms: ['telegram'], tags: ['вакансии'],
      scheduled_at: null, published_at: d(-12),
      views: 2890, reactions: 201, comments: 29, shares: 67,
      template_type: 'vacancy', created_at: d(-13), media: [], location_address: null, location_lat: null, location_lng: null,
    },
    {
      id: 9, title: 'Молодёжный форум «Возможности»', author_id: 1, author_name: 'Анна Королёва',
      content: 'Молодёжный форум объединит более 500 участников из 30 регионов России. Лекции, мастер-классы, нетворкинг, питч-сессии. Регистрация бесплатная для участников до 35 лет.',
      status: 'published', platforms: ['vk'], tags: ['мероприятия', 'молодёжь'],
      scheduled_at: null, published_at: d(-15),
      views: 8120, reactions: 634, comments: 98, shares: 211,
      template_type: 'announcement', created_at: d(-16), media: [], location_address: 'Казань, МВЦ «Казань Экспо»', location_lat: 55.775, location_lng: 49.200,
    },
    {
      id: 10, title: 'Итоги конкурса «Лучший проект года»', author_id: 1, author_name: 'Анна Королёва',
      content: 'Подведены итоги ежегодного конкурса проектов! 🏆 Первое место занял проект «ЭкоДвор» из Новосибирска. Поздравляем победителей и благодарим всех участников!',
      status: 'published', platforms: ['vk', 'telegram'], tags: ['новости'],
      scheduled_at: null, published_at: d(-20),
      views: 5200, reactions: 410, comments: 61, shares: 132,
      template_type: 'results', created_at: d(-21), media: [], location_address: null, location_lat: null, location_lng: null,
    },
  ]

  const notifications: Notification[] = [
    { id: 1, user_id: 1, message: 'Пост «Открытый конкурс грантов 2026» успешно опубликован во ВКонтакте', type: 'success', is_read: 0, created_at: d(-5) },
    { id: 2, user_id: 1, message: 'Новый комментарий к посту «Весенний хакатон»: «Отличная инициатива!»', type: 'info', is_read: 0, created_at: d(-3) },
    { id: 3, user_id: 1, message: 'Пост «Итоги I квартала 2026» запланирован на публикацию', type: 'info', is_read: 1, created_at: d(-1) },
    { id: 4, user_id: 1, message: 'Охват аудитории вырос на 15% за последние 7 дней 📈', type: 'success', is_read: 1, created_at: d(-2) },
    { id: 5, user_id: 1, message: 'Дмитрий Волков добавлен в группу «Официальный канал»', type: 'info', is_read: 0, created_at: d(0) },
  ]

  const groups: Group[] = [
    { id: 1, name: 'Официальный канал', description: 'Основная страница организации в соц. сетях', avatar: '', role: 'admin', created_by: 1, created_at: d(-30) },
    { id: 2, name: 'HR и вакансии', description: 'Публикации о найме и карьерных возможностях', avatar: '', role: 'editor', created_by: 1, created_at: d(-15) },
  ]

  const members: Record<number, GroupMember[]> = {
    1: [
      { id: 1, name: 'Анна Королёва', email: 'admin@mediahub.ru', avatar: '', role: 'admin', joined_at: d(-30) },
      { id: 2, name: 'Дмитрий Волков', email: 'editor@mediahub.ru', avatar: '', role: 'editor', joined_at: d(-20) },
    ],
    2: [
      { id: 1, name: 'Анна Королёва', email: 'admin@mediahub.ru', avatar: '', role: 'admin', joined_at: d(-15) },
      { id: 3, name: 'Светлана Михайлова', email: 'observer@mediahub.ru', avatar: '', role: 'observer', joined_at: d(-10) },
    ],
  }

  return {
    users, posts, notifications, groups, members,
    invites: { 1: [], 2: [] },
    nextId: { post: 11, user: 4, group: 3, notification: 6, invite: 1 },
  }
}

declare global { var __mockStore: Store | undefined }
if (!globalThis.__mockStore) globalThis.__mockStore = init()

export const store = globalThis.__mockStore

export const templates: Template[] = [
  {
    id: 1, name: 'Анонс мероприятия', type: 'announcement', description: 'Пост для анонса события, конференции или встречи',
    fields: [
      { key: 'event_name', label: 'Название мероприятия', placeholder: 'Хакатон «Цифровой регион»' },
      { key: 'date', label: 'Дата и время', placeholder: '15 мая 2026, 10:00' },
      { key: 'location', label: 'Место проведения', placeholder: 'Москва, ул. Пример, 1' },
      { key: 'description', label: 'Краткое описание', placeholder: 'Что будет происходить' },
    ],
    template_text: '',
  },
  {
    id: 2, name: 'Итоги / Результаты', type: 'results', description: 'Пост с итогами мероприятия, конкурса или периода',
    fields: [
      { key: 'event_name', label: 'Название события', placeholder: 'Конкурс проектов' },
      { key: 'key_results', label: 'Ключевые результаты', placeholder: '150 участников, 30 проектов' },
      { key: 'winner', label: 'Победитель / главный итог', placeholder: 'Проект «ЭкоДвор»' },
    ],
    template_text: '',
  },
  {
    id: 3, name: 'Вакансия', type: 'vacancy', description: 'Объявление об открытой вакансии',
    fields: [
      { key: 'position', label: 'Должность', placeholder: 'SMM-специалист' },
      { key: 'requirements', label: 'Требования', placeholder: 'Опыт от 2 лет, знание VK' },
      { key: 'conditions', label: 'Условия', placeholder: 'Удалённо, от 60 000 ₽' },
      { key: 'contacts', label: 'Контакты', placeholder: 'hr@company.ru' },
    ],
    template_text: '',
  },
  {
    id: 4, name: 'Грант / Конкурс', type: 'grant', description: 'Анонс конкурса грантов или финансирования',
    fields: [
      { key: 'grant_name', label: 'Название гранта', placeholder: 'Конкурс молодёжных проектов' },
      { key: 'amount', label: 'Размер финансирования', placeholder: 'до 500 000 ₽' },
      { key: 'deadline', label: 'Дедлайн подачи', placeholder: '30 мая 2026' },
      { key: 'requirements', label: 'Требования к участникам', placeholder: 'Возраст 18–35 лет' },
    ],
    template_text: '',
  },
]

export function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function nextId(key: string): number {
  return store.nextId[key]++
}
