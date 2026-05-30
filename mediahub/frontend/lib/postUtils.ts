export type EmojiSuggestion = {
  id: string
  label: string
  emoji: string
  count: number
}

type EmojiRule = {
  id: string
  label: string
  emoji: string
  pattern: RegExp
}

function makeWordPattern(words: string[], emojiGuard: string) {
  const source = words.join('|')
  return new RegExp(`(^|[^\\p{L}\\p{N}_])(${source})(?!\\s*${emojiGuard})(?=$|[^\\p{L}\\p{N}_])`, 'giu')
}

const EMOJI_RULES: EmojiRule[] = [
  { id: 'rose', label: 'Роза', emoji: '🌹', pattern: makeWordPattern(['роза', 'розы', 'розу', 'розе', 'розой'], '🌹') },
  { id: 'tulip', label: 'Тюльпан', emoji: '🌷', pattern: makeWordPattern(['тюльпан', 'тюльпаны', 'тюльпана', 'тюльпанов'], '🌷') },
  { id: 'sunflower', label: 'Подсолнух', emoji: '🌻', pattern: makeWordPattern(['подсолнух', 'подсолнухи', 'подсолнуха', 'подсолнухов'], '🌻') },
  { id: 'heart', label: 'Сердце', emoji: '❤️', pattern: makeWordPattern(['сердце', 'сердца', 'сердцем', 'сердцу'], '❤️') },
  { id: 'love', label: 'Любовь', emoji: '💖', pattern: makeWordPattern(['любовь', 'любви', 'любовью', 'любить', 'люблю'], '[❤️💖😍]') },
  { id: 'fire', label: 'Огонь', emoji: '🔥', pattern: makeWordPattern(['огонь', 'огня', 'огне', 'огнем'], '🔥') },
  { id: 'star', label: 'Звезда', emoji: '⭐', pattern: makeWordPattern(['звезда', 'звезды', 'звезду', 'звездой'], '[⭐🌟]') },
  { id: 'sparkles', label: 'Блеск', emoji: '✨', pattern: makeWordPattern(['блеск', 'сияние', 'сияет', 'сверкает', 'искры', 'искра'], '[✨💫]') },
  { id: 'sun', label: 'Солнце', emoji: '☀️', pattern: makeWordPattern(['солнце', 'солнца', 'солнцем', 'солнцу'], '☀️') },
  { id: 'moon', label: 'Луна', emoji: '🌙', pattern: makeWordPattern(['луна', 'луны', 'луну', 'луной', 'месяц'], '[🌙🌛🌜]') },
  { id: 'cloud', label: 'Облако', emoji: '☁️', pattern: makeWordPattern(['облако', 'облака', 'облаков', 'туча', 'тучи'], '☁️') },
  { id: 'rain', label: 'Дождь', emoji: '🌧️', pattern: makeWordPattern(['дождь', 'дождя', 'дожди', 'ливень', 'ливня'], '[🌧️☔]') },
  { id: 'snow', label: 'Снег', emoji: '❄️', pattern: makeWordPattern(['снег', 'снега', 'снежный', 'снежинка', 'снежинки'], '[❄️☃️]') },
  { id: 'rainbow', label: 'Радуга', emoji: '🌈', pattern: makeWordPattern(['радуга', 'радуги', 'радугу'], '🌈') },
  { id: 'lightning', label: 'Молния', emoji: '⚡', pattern: makeWordPattern(['молния', 'молнии', 'гроза', 'грозы'], '[⚡⛈️]') },
  { id: 'wind', label: 'Ветер', emoji: '💨', pattern: makeWordPattern(['ветер', 'ветра', 'ветром', 'ветреный'], '💨') },
  { id: 'flower', label: 'Цветок', emoji: '🌸', pattern: makeWordPattern(['цветок', 'цветы', 'цветка', 'цветов'], '[🌸🌺💐]') },
  { id: 'tree', label: 'Дерево', emoji: '🌳', pattern: makeWordPattern(['дерево', 'деревья', 'деревом', 'лес', 'леса'], '[🌳🌲]') },
  { id: 'leaf', label: 'Листья', emoji: '🍃', pattern: makeWordPattern(['лист', 'листья', 'листвы', 'листопад'], '[🍃🍂]') },
  { id: 'apple', label: 'Яблоко', emoji: '🍎', pattern: makeWordPattern(['яблоко', 'яблоки', 'яблока', 'яблок'], '🍎') },
  { id: 'cherry', label: 'Вишня', emoji: '🍒', pattern: makeWordPattern(['вишня', 'вишни', 'вишню', 'черешня', 'черешни'], '🍒') },
  { id: 'lemon', label: 'Лимон', emoji: '🍋', pattern: makeWordPattern(['лимон', 'лимоны', 'лимона', 'лимонов'], '🍋') },
  { id: 'watermelon', label: 'Арбуз', emoji: '🍉', pattern: makeWordPattern(['арбуз', 'арбузы', 'арбуза', 'арбузов'], '🍉') },
  { id: 'strawberry', label: 'Клубника', emoji: '🍓', pattern: makeWordPattern(['клубника', 'клубники', 'клубнику', 'ягода', 'ягоды'], '[🍓🫐]') },
  { id: 'cake', label: 'Торт', emoji: '🎂', pattern: makeWordPattern(['торт', 'торта', 'торты', 'пирожное', 'десерт'], '[🎂🍰🧁]') },
  { id: 'icecream', label: 'Мороженое', emoji: '🍦', pattern: makeWordPattern(['мороженое', 'мороженого', 'мороженым'], '[🍦🍨]') },
  { id: 'coffee', label: 'Кофе', emoji: '☕', pattern: makeWordPattern(['кофе', 'кофейный', 'капучино', 'латте'], '☕') },
  { id: 'tea', label: 'Чай', emoji: '🍵', pattern: makeWordPattern(['чай', 'чая', 'чаю', 'чайный'], '[🍵☕]') },
  { id: 'pizza', label: 'Пицца', emoji: '🍕', pattern: makeWordPattern(['пицца', 'пиццы', 'пиццу'], '🍕') },
  { id: 'burger', label: 'Бургер', emoji: '🍔', pattern: makeWordPattern(['бургер', 'бургеры', 'бургера'], '🍔') },
  { id: 'bread', label: 'Хлеб', emoji: '🥖', pattern: makeWordPattern(['хлеб', 'хлеба', 'булка', 'булочки'], '[🥖🍞]') },
  { id: 'music', label: 'Музыка', emoji: '🎵', pattern: makeWordPattern(['музыка', 'музыки', 'музыку', 'музыкой'], '🎵') },
  { id: 'microphone', label: 'Песня', emoji: '🎤', pattern: makeWordPattern(['песня', 'песни', 'петь', 'вокал', 'вокалист'], '[🎤🎶]') },
  { id: 'guitar', label: 'Гитара', emoji: '🎸', pattern: makeWordPattern(['гитара', 'гитары', 'гитару', 'рок'], '[🎸🤘]') },
  { id: 'dance', label: 'Танец', emoji: '💃', pattern: makeWordPattern(['танец', 'танцы', 'танцевать', 'танцпол'], '[💃🕺]') },
  { id: 'movie', label: 'Кино', emoji: '🎬', pattern: makeWordPattern(['кино', 'фильм', 'фильмы', 'съёмка', 'съемка'], '[🎬🎥]') },
  { id: 'camera', label: 'Фото', emoji: '📸', pattern: makeWordPattern(['фото', 'фотография', 'фотосессия', 'камера', 'снимок'], '[📸📷]') },
  { id: 'book', label: 'Книга', emoji: '📚', pattern: makeWordPattern(['книга', 'книги', 'читать', 'чтение', 'библиотека'], '[📚📖]') },
  { id: 'art', label: 'Искусство', emoji: '🎨', pattern: makeWordPattern(['искусство', 'рисунок', 'рисовать', 'картина', 'творчество'], '[🎨🖌️]') },
  { id: 'sport', label: 'Спорт', emoji: '⚽', pattern: makeWordPattern(['спорт', 'спорта', 'спортом'], '[⚽🏆]') },
  { id: 'football', label: 'Футбол', emoji: '⚽', pattern: makeWordPattern(['футбол', 'футбольный', 'матч'], '⚽') },
  { id: 'basketball', label: 'Баскетбол', emoji: '🏀', pattern: makeWordPattern(['баскетбол', 'баскетбольный'], '🏀') },
  { id: 'volleyball', label: 'Волейбол', emoji: '🏐', pattern: makeWordPattern(['волейбол', 'волейбольный'], '🏐') },
  { id: 'tennis', label: 'Теннис', emoji: '🎾', pattern: makeWordPattern(['теннис', 'теннисный', 'ракетка'], '🎾') },
  { id: 'running', label: 'Бег', emoji: '🏃', pattern: makeWordPattern(['бег', 'бежать', 'пробежка', 'марафон'], '[🏃🏅]') },
  { id: 'medal', label: 'Победа', emoji: '🏅', pattern: makeWordPattern(['победа', 'победы', 'победить', 'чемпион', 'чемпионат'], '[🏅🏆]') },
  { id: 'party', label: 'Праздник', emoji: '🎉', pattern: makeWordPattern(['праздник', 'праздники', 'праздничный', 'вечеринка'], '[🎉🎊]') },
  { id: 'gift', label: 'Подарок', emoji: '🎁', pattern: makeWordPattern(['подарок', 'подарки', 'сюрприз', 'сюрпризы'], '🎁') },
  { id: 'balloon', label: 'Шарики', emoji: '🎈', pattern: makeWordPattern(['шар', 'шары', 'шарики', 'воздушный шар'], '🎈') },
  { id: 'birthday', label: 'День рождения', emoji: '🥳', pattern: makeWordPattern(['день рождения', 'именинник', 'именинница', 'юбилей'], '[🥳🎂]') },
  { id: 'christmas', label: 'Новый год', emoji: '🎄', pattern: makeWordPattern(['новый год', 'елка', 'ёлка', 'елки', 'ёлки'], '[🎄✨]') },
  { id: 'school', label: 'Школа', emoji: '🏫', pattern: makeWordPattern(['школа', 'школы', 'урок', 'уроки', 'класс'], '[🏫📚]') },
  { id: 'graduate', label: 'Учёба', emoji: '🎓', pattern: makeWordPattern(['учёба', 'учеба', 'студент', 'студенты', 'выпуск', 'выпускник'], '[🎓📘]') },
  { id: 'briefcase', label: 'Работа', emoji: '💼', pattern: makeWordPattern(['работа', 'работы', 'вакансия', 'карьера', 'офис'], '[💼📈]') },
  { id: 'rocket', label: 'Старт', emoji: '🚀', pattern: makeWordPattern(['старт', 'запуск', 'прорыв', 'успех', 'стартап'], '[🚀✨]') },
  { id: 'idea', label: 'Идея', emoji: '💡', pattern: makeWordPattern(['идея', 'идеи', 'придумал', 'вдохновение', 'инсайт'], '[💡✨]') },
  { id: 'computer', label: 'Технологии', emoji: '💻', pattern: makeWordPattern(['компьютер', 'ноутбук', 'код', 'программирование', 'технологии', 'айти', 'it'], '[💻🖥️]') },
  { id: 'phone', label: 'Телефон', emoji: '📱', pattern: makeWordPattern(['телефон', 'смартфон', 'мобильный'], '[📱☎️]') },
  { id: 'mail', label: 'Сообщение', emoji: '✉️', pattern: makeWordPattern(['письмо', 'сообщение', 'почта', 'email', 'емейл'], '[✉️📩]') },
  { id: 'bell', label: 'Напоминание', emoji: '🔔', pattern: makeWordPattern(['напоминание', 'уведомление', 'звонок', 'оповещение'], '[🔔📣]') },
  { id: 'calendar', label: 'Дата', emoji: '📅', pattern: makeWordPattern(['дата', 'календарь', 'расписание', 'график'], '[📅🗓️]') },
  { id: 'clock', label: 'Время', emoji: '⏰', pattern: makeWordPattern(['время', 'час', 'часы', 'таймер', 'срок'], '[⏰⌛]') },
  { id: 'pin', label: 'Место', emoji: '📍', pattern: makeWordPattern(['место', 'локация', 'адрес', 'площадка'], '[📍🗺️]') },
  { id: 'travel', label: 'Путешествие', emoji: '✈️', pattern: makeWordPattern(['путешествие', 'поездка', 'тур', 'самолет', 'самолёт', 'перелет', 'перелёт'], '[✈️🧳]') },
  { id: 'car', label: 'Машина', emoji: '🚗', pattern: makeWordPattern(['машина', 'авто', 'автомобиль', 'дорога'], '[🚗🛣️]') },
  { id: 'bike', label: 'Велосипед', emoji: '🚲', pattern: makeWordPattern(['велосипед', 'велосипеды', 'велозаезд'], '🚲') },
  { id: 'train', label: 'Поезд', emoji: '🚆', pattern: makeWordPattern(['поезд', 'поезда', 'вагон', 'электричка'], '[🚆🚉]') },
  { id: 'home', label: 'Дом', emoji: '🏠', pattern: makeWordPattern(['дом', 'дома', 'квартира', 'уют'], '[🏠🏡]') },
  { id: 'cat', label: 'Кот', emoji: '🐱', pattern: makeWordPattern(['кот', 'коты', 'кошка', 'кошки', 'котик'], '[🐱😺]') },
  { id: 'dog', label: 'Собака', emoji: '🐶', pattern: makeWordPattern(['собака', 'собаки', 'пес', 'пёс', 'щенок'], '[🐶🐕]') },
  { id: 'bird', label: 'Птица', emoji: '🐦', pattern: makeWordPattern(['птица', 'птицы', 'птичка', 'птички'], '[🐦🕊️]') },
  { id: 'butterfly', label: 'Бабочка', emoji: '🦋', pattern: makeWordPattern(['бабочка', 'бабочки', 'бабочку'], '🦋') },
  { id: 'bee', label: 'Пчела', emoji: '🐝', pattern: makeWordPattern(['пчела', 'пчелы', 'пчёлы', 'мед', 'мёд'], '[🐝🍯]') },
  { id: 'paw', label: 'Лапки', emoji: '🐾', pattern: makeWordPattern(['лапа', 'лапы', 'лапки'], '🐾') },
  { id: 'baby', label: 'Дети', emoji: '👶', pattern: makeWordPattern(['ребенок', 'ребёнок', 'дети', 'малыш', 'малыши'], '[👶🧒]') },
  { id: 'family', label: 'Семья', emoji: '👨‍👩‍👧‍👦', pattern: makeWordPattern(['семья', 'семьи', 'семейный', 'родители'], '👨‍👩‍👧‍👦') },
  { id: 'friends', label: 'Друзья', emoji: '🫶', pattern: makeWordPattern(['друг', 'друзья', 'дружба', 'подруга', 'товарищи'], '[🫶🤝]') },
  { id: 'smile', label: 'Радость', emoji: '😊', pattern: makeWordPattern(['радость', 'радоваться', 'улыбка', 'счастье', 'счастливый'], '[😊😄😁]') },
  { id: 'cool', label: 'Круто', emoji: '😎', pattern: makeWordPattern(['круто', 'классно', 'стильно', 'модно', 'кайф'], '[😎🔥]') },
  { id: 'wow', label: 'Вау', emoji: '🤩', pattern: makeWordPattern(['вау', 'впечатляет', 'восторг', 'восхищение'], '[🤩✨]') },
  { id: 'clap', label: 'Аплодисменты', emoji: '👏', pattern: makeWordPattern(['аплодисменты', 'браво', 'похвала', 'молодцы'], '👏') },
  { id: 'warning', label: 'Внимание', emoji: '⚠️', pattern: makeWordPattern(['важно', 'внимание', 'осторожно', 'предупреждение'], '[⚠️❗]') },
  { id: 'check', label: 'Готово', emoji: '✅', pattern: makeWordPattern(['готово', 'готовность', 'успешно', 'выполнено'], '✅') },
  { id: 'question', label: 'Вопрос', emoji: '❓', pattern: makeWordPattern(['вопрос', 'непонятно', 'уточнение', 'почему'], '❓') },
]

function countMatches(pattern: RegExp, text: string) {
  const matches = text.match(pattern)
  return matches ? matches.length : 0
}

export function getEmojiSuggestions(text: string): EmojiSuggestion[] {
  return EMOJI_RULES
    .map((rule) => ({
      id: rule.id,
      label: rule.label,
      emoji: rule.emoji,
      count: countMatches(rule.pattern, text),
    }))
    .filter((item) => item.count > 0)
}

export function applyEmojiSuggestion(text: string, suggestionId: string) {
  const rule = EMOJI_RULES.find((item) => item.id === suggestionId)
  if (!rule) return text
  return text.replace(rule.pattern, `$1$2 ${rule.emoji}`)
}
