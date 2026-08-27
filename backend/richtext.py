"""
Ссылки внутри текста поста.

Задача простая на вид: автор хочет, чтобы слово было кликабельным. Но
площадки устроены по-разному, и одна разметка обязана разворачиваться в две
разные вещи:

* **Telegram** умеет гиперссылки — `<a href="…">текст</a>` при `parse_mode=HTML`.
* **ВКонтакте в тексте записи их не умеет вовсе.** В wall.post нет ни HTML, ни
  разметки: ссылкой становится только сам видимый URL. Поэтому там
  «текст (адрес)» — не компромисс от лени, а единственный доступный вид.

Разметка выбрана как в Markdown — `[текст](https://…)`: её узнают, она не
конфликтует с подстановками группы (`{{ключ}}`) и с полями шаблонов (`{поле}`),
и её легко набрать руками.

**Экранируем всегда, а не только при наличии ссылок.** Как только в сообщении
включён parse_mode, любой «<» в тексте человека ломает отправку целиком.
Половинчатое «включаем HTML, только если есть ссылка» означало бы, что пост
уходит или не уходит в зависимости от того, что автор написал, — и падал бы
ровно тогда, когда его никто не ждёт.
"""
import html
import re

# [текст](адрес). Текст без переносов и без вложенных скобок: разбирать
# вложенность регулярным выражением бессмысленно, а на практике её не бывает.
LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")


def segments(text: str) -> list[tuple[str, str, str]]:
    """
    Разбирает текст на куски: ('text', содержимое, '') и ('link', подпись, адрес).

    Промежуточное представление нужно ради длины: у Telegram предел считается
    по видимым символам, а не по разметке. Резать готовый HTML по длине —
    верный способ разорвать тег пополам и получить отказ вместо публикации.
    """
    parts: list[tuple[str, str, str]] = []
    position = 0
    for match in LINK_RE.finditer(text or ""):
        if match.start() > position:
            parts.append(("text", text[position:match.start()], ""))
        parts.append(("link", match.group(1), match.group(2)))
        position = match.end()
    if position < len(text or ""):
        parts.append(("text", text[position:], ""))
    return parts


def has_links(text: str) -> bool:
    return bool(LINK_RE.search(text or ""))


def to_plain(text: str) -> str:
    """
    Вид для площадок без гиперссылок — ВКонтакте.

    Адрес выносим в скобки следом за подписью: сам по себе он станет ссылкой,
    а подпись объяснит, куда она ведёт. Если подпись и есть адрес, скобки не
    добавляем — «https://a.ru (https://a.ru)» выглядит поломкой.
    """
    out = []
    for kind, body, url in segments(text):
        if kind == "text":
            out.append(body)
        elif body.strip() == url:
            out.append(url)
        else:
            out.append(f"{body} ({url})")
    return "".join(out)


def to_html(text: str) -> str:
    """Вид для Telegram: экранированный текст со ссылками."""
    out = []
    for kind, body, url in segments(text):
        if kind == "text":
            out.append(html.escape(body, quote=False))
        else:
            out.append(f'<a href="{html.escape(url, quote=True)}">'
                       f"{html.escape(body, quote=False)}</a>")
    return "".join(out)


def visible_length(text: str) -> int:
    """Длина в том виде, в каком её считает Telegram: без разметки."""
    return sum(len(body) for _, body, _ in segments(text))


def chunks(text: str, limit: int) -> list[str]:
    """
    Режет текст на части по видимой длине, не разрывая ссылок.

    Ссылка, которая не помещается в остаток, целиком уезжает в следующую
    часть: разорванная пополам, она превратилась бы в сломанный тег и отказ
    Telegram, а не в две половинки подписи.
    """
    result: list[str] = []
    current: list[str] = []
    used = 0

    def flush() -> None:
        nonlocal current, used
        if current:
            result.append("".join(current))
        current, used = [], 0

    for kind, body, url in segments(text):
        if kind == "link":
            piece = f"[{body}]({url})"
            if used + len(body) > limit:
                flush()
            current.append(piece)
            used += len(body)
            continue
        # Обычный текст режется где угодно, поэтому набиваем им остаток.
        rest = body
        while rest:
            space = limit - used
            if space <= 0:
                flush()
                space = limit
            current.append(rest[:space])
            used += len(rest[:space])
            rest = rest[space:]
    flush()
    return result or [""]


def truncate(text: str, limit: int) -> str:
    """
    Обрезает по видимой длине. Ссылка, не влезшая целиком, отбрасывается —
    оборванный тег Telegram не примет, а половина адреса всё равно бесполезна.
    """
    if visible_length(text) <= limit:
        return text
    return chunks(text, limit)[0]
