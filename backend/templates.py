"""
Шаблоны постов, в том числе свои.

Встроенных было четыре, и правились они только миграцией. Центру, который
каждую неделю выпускает одно и то же объявление, приходилось набирать рыбу
заново — при том что механика подстановки полей уже существовала.

**Поля выводятся из текста, а не описываются отдельно.** Просить человека
завести список полей с ключами, подписями и подсказками — значит просить его
поработать программистом. Он пишет «Ждём вас на {название} — {дата}», а поля
из этого видны и так. Ключ он же и подпись: выдумывать вторую сущность там,
где хватает одной, незачем.

Разметка `{поле}` — та же, что у встроенных шаблонов. Она не пересекается ни с
подстановками группы (`{{ключ}}`), ни со ссылками (`[текст](адрес)`), поэтому
всё это спокойно живёт в одном тексте.
"""
import re

from fastapi import HTTPException

# {поле}. Одна пара скобок и без вложенных — двойные заняты подстановками
# группы, и захватывать их здесь нельзя.
FIELD_RE = re.compile(r"(?<!\{)\{([^{}\n]{1,60})\}(?!\})")

# Латиница и цифры для type: он попадает в posts.template_type и в адреса,
# а кириллический слаг там читается плохо и ломает сравнение при регистре.
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

MAX_FIELDS = 12


def extract_fields(*texts: str) -> list[dict]:
    """
    Поля шаблона в том порядке, в каком они встречаются в тексте.

    Порядок важен: по нему рисуется форма заполнения, и вопросы должны идти
    так же, как в самом объявлении, — иначе человек заполняет вразнобой.
    """
    fields: list[dict] = []
    seen: set[str] = set()
    for text in texts:
        for match in FIELD_RE.finditer(text or ""):
            key = match.group(1).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            fields.append({"key": key, "label": key, "placeholder": ""})
    if len(fields) > MAX_FIELDS:
        raise HTTPException(
            400,
            f"В шаблоне слишком много полей ({len(fields)}). "
            f"Оставьте не больше {MAX_FIELDS} — иначе заполнять его будет дольше, "
            "чем написать пост руками.",
        )
    return fields


def slug(name: str, gid: int) -> str:
    """
    Идентификатор шаблона. Попадает в `posts.template_type`, поэтому должен
    быть устойчивым и читаемым — по нему потом видно, из чего сделан пост.
    """
    base = (name or "").strip().lower().translate(TRANSLIT)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40]
    return f"g{gid}-{base or 'shablon'}"


def render(template_text: str, values: dict) -> str:
    """Подставляет значения полей. Незаполненное поле остаётся видимым."""
    def replace(match: re.Match) -> str:
        value = values.get(match.group(1).strip())
        return str(value) if value not in (None, "") else match.group(0)

    return FIELD_RE.sub(replace, template_text or "")


def serialize(row) -> dict:
    from utils import as_json_list, fmt_dt

    d = dict(row)
    d["fields"] = as_json_list(d.get("fields"))
    d["created_at"] = fmt_dt(d.get("created_at"))
    # Встроенные шаблоны править нельзя: они общие для всех групп, и правка
    # одной группы меняла бы их всем остальным.
    d["editable"] = d.get("group_id") is not None
    return d


def visible_to(conn, user_id: int) -> list[dict]:
    """
    Встроенные шаблоны плюс шаблоны групп, где человек состоит.

    Шаблон — часть того, как публикует конкретное учреждение; показывать его
    посторонним незачем, а иногда и нельзя: в тексте вполне может быть
    внутренняя формулировка.
    """
    c = conn.cursor()
    c.execute(
        "SELECT t.* FROM templates t "
        "WHERE t.group_id IS NULL OR t.group_id IN ("
        "  SELECT group_id FROM group_members WHERE user_id=%s) "
        "ORDER BY t.group_id NULLS FIRST, t.name",
        (user_id,),
    )
    return [serialize(r) for r in c.fetchall()]


def find(conn, template_type: str, user_id: int) -> dict:
    """Шаблон по идентификатору — только из доступных этому человеку."""
    c = conn.cursor()
    c.execute(
        "SELECT t.* FROM templates t "
        "WHERE t.type=%s AND (t.group_id IS NULL OR t.group_id IN ("
        "  SELECT group_id FROM group_members WHERE user_id=%s)) "
        "LIMIT 1",
        (template_type, user_id),
    )
    row = c.fetchone()
    if not row:
        raise HTTPException(404, "Шаблон не найден")
    return serialize(row)
