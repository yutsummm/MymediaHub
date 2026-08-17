"""
Что происходит с текстом поста между редактором и соцсетью.

Две обработки, обе — **на выпуске, а не при сохранении**:

* подстановка переменных группы (`{{центр}}`, `{{адрес}}`);
* разметка ссылок UTM-метками.

Почему на выпуске. Хранимый текст — это то, что человек написал: открыв пост
завтра, он обязан увидеть свои слова, а не результат чужой обработки. К тому
же UTM зависит от площадки — одна и та же ссылка уходит в ВК с
`utm_source=vk`, а в Telegram с `utm_source=telegram`, — и в одном хранимом
тексте это просто не помещается.

Обратная сторона — человек не видит финального текста в редакторе. Поэтому
редактор показывает предпросмотр с подстановками: договор «что вижу, то и
выйдет» держится предпросмотром, а не тем, что мы портим исходник.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# {{ключ}} — с пробелами внутри скобок или без. Ключ — слово из букв, цифр,
# дефиса и подчёркивания: скобки в обычном тексте встречаются, и превращать
# в подстановку всё подряд между ними нельзя.
VARIABLE_RE = re.compile(r"\{\{\s*([\w\-]+)\s*\}\}")

# Ссылка в тексте поста. Хвостовая пунктуация в адрес не входит: «зайдите на
# https://example.ru.» — это ссылка и точка, а не ссылка с точкой.
URL_RE = re.compile(r"https?://[^\s<>\"']+")
_TRAILING = ".,;:!?)»\"'"

# Метки, которые проставляем. Значение campaign задаёт рубрика поста —
# именно её и хотят различать в статистике сайта: «сколько пришло с анонсов
# мероприятий» против «сколько с грантов».
UTM_MEDIUM = "social"
PLATFORM_SOURCE = {"vk": "vk", "telegram": "telegram"}


def apply_variables(text: str, variables: dict | None) -> str:
    """
    Подставляет значения переменных группы.

    Неизвестный ключ остаётся как есть — `{{телефон}}` в тексте видно сразу,
    а молча вырезанная подстановка выглядит как оговорка автора и уходит в
    паблик незамеченной.
    """
    if not text or not variables:
        return text or ""

    def replace(match: re.Match) -> str:
        value = variables.get(match.group(1))
        return str(value) if value not in (None, "") else match.group(0)

    return VARIABLE_RE.sub(replace, text)


def _tag_url(url: str, source: str, campaign: str | None) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    # Свои метки не трогаем: если человек принёс ссылку из рекламного
    # кабинета, у неё уже есть разметка, и перебивать её — терять данные.
    if any(key.startswith("utm_") for key in query):
        return url
    query["utm_source"] = source
    query["utm_medium"] = UTM_MEDIUM
    if campaign:
        query["utm_campaign"] = campaign
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


def apply_utm(text: str, platform: str, tags: list | None) -> str:
    """
    Размечает ссылки в тексте метками площадки.

    Без меток любой переход из соцсети виден в статистике сайта как «прямой
    заход», и вопрос «сколько людей к нам пришло из ВК» остаётся без ответа
    навсегда — задним числом это не восстановить.
    """
    if not text:
        return text or ""
    source = PLATFORM_SOURCE.get(platform)
    if not source:
        return text
    campaign = None
    for tag in (tags or []):
        if isinstance(tag, str) and tag.strip():
            campaign = tag.strip()
            break

    def replace(match: re.Match) -> str:
        url = match.group(0)
        trailing = ""
        while url and url[-1] in _TRAILING:
            trailing = url[-1] + trailing
            url = url[:-1]
        if not url:
            return match.group(0)
        return _tag_url(url, source, campaign) + trailing

    return URL_RE.sub(replace, text)


def prepare(text: str, *, platform: str, variables: dict | None,
            tags: list | None, utm_enabled: bool) -> str:
    """
    Текст в том виде, в каком он уйдёт на площадку.

    Порядок важен: переменные подставляются первыми — значение вполне может
    содержать ссылку (адрес сайта центра), и её тоже нужно разметить.
    """
    result = apply_variables(text, variables)
    if utm_enabled:
        result = apply_utm(result, platform, tags)
    return result
