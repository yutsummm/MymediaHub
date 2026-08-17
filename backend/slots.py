"""
Расписание публикаций: очередь по слотам вместо даты у каждого поста.

Раньше у каждого отложенного поста дату выбирали руками. Для центра, который
публикует через день, это одна и та же работа по десять раз в месяц: человек
каждый раз заново вспоминает, когда он обычно выкладывает, и вручную
выстраивает посты, чтобы они не столкнулись.

Слот описывает привычку — «понедельник, среда, пятница в 12:00». Пост,
поставленный в очередь, занимает ближайшее свободное окно.

**Очередь не пересобирается.** Buffer при удалении поста подтягивает
остальные вперёд; мы этого сознательно не делаем. Пост здесь — чаще всего
анонс мероприятия, привязанный к дате: сдвинуть его на два дня раньше без
ведома автора хуже, чем оставить в расписании дырку. Занятое окно
освобождается, но соседи остаются на своих местах.

**Слот превращается в обычный `scheduled_at` сразу.** Отдельного состояния
«в очереди» нет: сервер считает конкретное время и записывает его в пост.
Так очередь не становится вторым механизмом публикации рядом с планировщиком,
пост виден в календаре, и человеку есть что назвать, отвечая на вопрос
«когда это выйдет».
"""
from datetime import datetime, time, timedelta

from fastapi import HTTPException

from utils import app_now

# 0 — понедельник, как у datetime.weekday(). Считать дни недели двумя
# способами в одном проекте — верный путь к посту, вышедшему не в тот день.
WEEKDAYS_RU = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")

# Насколько далеко вперёд ищем окно. Четыре недели — это уже сигнал, что
# расписание не поспевает за потоком постов, и об этом лучше сказать, чем
# назначить публикацию на позапрошлый год.
SEARCH_HORIZON_DAYS = 28


def list_slots(conn, gid: int) -> list[dict]:
    c = conn.cursor()
    c.execute(
        "SELECT id, weekday, at FROM publishing_slots WHERE group_id=%s "
        "ORDER BY weekday, at",
        (gid,),
    )
    return [
        {"id": r["id"], "weekday": r["weekday"], "at": r["at"].strftime("%H:%M"),
         "weekday_label": WEEKDAYS_RU[r["weekday"]]}
        for r in c.fetchall()
    ]


def _parse_time(value: str) -> time:
    try:
        hh, mm = str(value).split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        raise HTTPException(400, f"Некорректное время слота: {value!r}. Ожидается ЧЧ:ММ")


def replace_slots(conn, gid: int, slots: list[dict]) -> list[dict]:
    """
    Заменяет расписание группы целиком.

    Целиком, а не по одному: расписание человек воспринимает как одну вещь —
    сетку недели, — и правит её тоже целиком. Точечные добавления и удаления
    заставили бы интерфейс держать состояние каждого слота по отдельности
    ради того же результата.
    """
    seen: set[tuple[int, time]] = set()
    cleaned: list[tuple[int, time]] = []
    for slot in slots:
        weekday = slot.get("weekday")
        if not isinstance(weekday, int) or not 0 <= weekday <= 6:
            raise HTTPException(400, "День недели задаётся числом от 0 (понедельник) до 6")
        at = _parse_time(slot.get("at", ""))
        key = (weekday, at)
        # Повтор — это опечатка, а не «два места в это время»: расписание
        # описывает привычку, а не количество мест.
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(key)

    c = conn.cursor()
    c.execute("DELETE FROM publishing_slots WHERE group_id=%s", (gid,))
    for weekday, at in cleaned:
        c.execute(
            "INSERT INTO publishing_slots (group_id, weekday, at) VALUES (%s, %s, %s)",
            (gid, weekday, at),
        )
    conn.commit()
    return list_slots(conn, gid)


def _slot_moments(slots: list[tuple[int, time]], since: datetime) -> list[datetime]:
    """Все моменты расписания на горизонте поиска, по возрастанию."""
    moments = []
    for day_offset in range(SEARCH_HORIZON_DAYS + 1):
        day = (since + timedelta(days=day_offset)).date()
        for weekday, at in slots:
            if day.weekday() != weekday:
                continue
            moment = datetime.combine(day, at, tzinfo=since.tzinfo)
            if moment > since:
                moments.append(moment)
    return sorted(moments)


def next_free_slot(conn, gid: int, *, exclude_post_id: int | None = None) -> datetime:
    """
    Ближайшее свободное окно расписания.

    Занятым считается окно, на которое уже назначен пост этой группы —
    неважно, поставили его через очередь или выбрали дату руками. Расписание
    описывает, когда группа публикует; два поста в одну минуту не были бы
    двумя записями подряд, а перебили бы друг друга в ленте.
    """
    c = conn.cursor()
    c.execute(
        "SELECT weekday, at FROM publishing_slots WHERE group_id=%s ORDER BY weekday, at",
        (gid,),
    )
    slots = [(r["weekday"], r["at"]) for r in c.fetchall()]
    if not slots:
        raise HTTPException(
            409,
            "Расписание публикаций не задано. Укажите дни и время в настройках группы "
            "или выберите дату вручную.",
        )

    now = app_now()
    c.execute(
        "SELECT scheduled_at FROM posts "
        "WHERE group_id=%s AND status IN ('scheduled','on_review') "
        "  AND scheduled_at IS NOT NULL AND scheduled_at > %s "
        "  AND (%s::int IS NULL OR id <> %s::int)",
        (gid, now, exclude_post_id, exclude_post_id),
    )
    taken = {row["scheduled_at"] for row in c.fetchall()}

    for moment in _slot_moments(slots, now):
        if not any(abs((moment - busy).total_seconds()) < 60 for busy in taken):
            return moment

    raise HTTPException(
        409,
        f"В расписании нет свободного времени на ближайшие {SEARCH_HORIZON_DAYS} дней. "
        "Добавьте слоты или назначьте дату вручную.",
    )
