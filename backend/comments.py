"""
Обращения под публикациями и срок ответа на них.

С 1 декабря 2022 года учреждения обязаны не только вести официальные страницы
в соцсетях, но и отвечать на вопросы граждан в комментариях; за сроками следит
«Инцидент менеджмент». Для молодёжного центра это не удобство, а обязанность,
и единственный инструмент, который у него до сих пор был, — заходить в ВК и
листать ленту руками.

Здесь три вещи: вычитывание комментариев, определение «отвечено ли» и
предупреждение, когда срок вот-вот выйдет.

**Только ВКонтакте, и это осознанно.** В Telegram комментарии живут в
отдельной группе обсуждений, куда бот попадает не всегда: обещать очередь
обращений, которая работает через раз, хуже, чем честно сказать «пока только
ВК». То же решение мы уже принимали по первому комментарию.

**Как определяется ответ.** Комментарий от лица сообщества, отвечающий на
конкретное обращение, закрывает его. Комментарий от сообщества без указания
адресата закрывает все обращения под этой записью, оставленные до него, —
так люди и отвечают, когда вопрос в ветке один. Правило неточное в обе
стороны, но ошибается оно в сторону «отвечено», только когда сообщество
действительно что-то написало под записью; молчание не закроет ничего
никогда.
"""
import os
from datetime import UTC, timedelta

import health
from logs import get_logger
from utils import app_now, decrypt_row_secret, get_db, parse_dt, vk_get_comments

log = get_logger("comments")

COMMENTS_ENABLED = os.getenv("COMMENTS_ENABLED", "1").strip().lower() not in ("0", "false", "no")
# Как часто заглядывать под публикации. Срок ответа считается часами, поэтому
# минута точности не нужна, а лишний такт — это запрос к ВК на каждый пост.
POLL_INTERVAL = int(os.getenv("COMMENTS_POLL_SECONDS", "600"))
# Насколько старые публикации ещё проверяем. Под постом полугодовой давности
# новый вопрос — редкость, а обходить весь архив каждые десять минут дорого.
LOOKBACK_DAYS = int(os.getenv("COMMENTS_LOOKBACK_DAYS", "14"))
# Сколько записей берём за такт: у центра их немного, но лезть за всеми сразу
# после долгого простоя незачем.
MAX_POSTS_PER_TICK = int(os.getenv("COMMENTS_MAX_POSTS", "40"))

# Доля срока, после которой пора предупреждать. Предупреждать в момент
# наступления срока бессмысленно — он уже вышел.
WARN_AT = 0.75


def _connected_groups(conn) -> list[dict]:
    """Группы с подключённым ВК: у остальных читать нечего."""
    c = conn.cursor()
    c.execute(
        "SELECT g.id, g.name, g.reply_sla_hours, v.group_id AS vk_group_id, v.access_token "
        "FROM groups g JOIN vk_settings v ON v.workspace_id = g.id"
    )
    groups = []
    for row in c.fetchall():
        vk = decrypt_row_secret(row, "access_token")
        if vk and vk.get("access_token"):
            groups.append(dict(vk))
    return groups


def _recent_posts(conn, gid: int) -> list[dict]:
    c = conn.cursor()
    c.execute(
        "SELECT id, vk_post_id FROM posts "
        "WHERE group_id=%s AND status='published' AND vk_post_id IS NOT NULL "
        "  AND vk_post_id <> '' AND published_at > %s "
        "ORDER BY published_at DESC LIMIT %s",
        (gid, app_now() - timedelta(days=LOOKBACK_DAYS), MAX_POSTS_PER_TICK),
    )
    return [dict(r) for r in c.fetchall()]


def _flatten(response: dict) -> list[dict]:
    """Комментарии и ответы внутри веток — одним списком."""
    items = list(response.get("items") or [])
    for item in list(items):
        thread = (item.get("thread") or {}).get("items") or []
        items.extend(thread)
    return items


def _names(response: dict) -> dict:
    """Идентификатор автора → имя. Люди и сообщества лежат в разных списках."""
    names = {}
    for profile in response.get("profiles") or []:
        full = " ".join(x for x in (profile.get("first_name"), profile.get("last_name")) if x)
        names[str(profile.get("id"))] = full or "Пользователь"
    for group in response.get("groups") or []:
        names[f"-{group.get('id')}"] = group.get("name") or "Сообщество"
    return names


def _first_pass(conn, gid: int) -> bool:
    """
    Видим эту группу впервые?

    При первом вычитывании приходит вся история за две недели, и часть её —
    давно провисевшие без ответа обращения. Предупреждать о каждом значило бы
    вывалить архив в уведомления как новости: администратор получил бы два
    десятка сообщений о том, чего уже не поправить, и перестал бы читать их
    вообще. В очереди эти обращения видны и помечены просроченными — там им
    и место.
    """
    c = conn.cursor()
    c.execute("SELECT 1 FROM post_comments WHERE group_id=%s LIMIT 1", (gid,))
    return c.fetchone() is None


def _store(conn, post: dict, gid: int, vk_group_id: str, response: dict,
           first_pass: bool = False) -> int:
    """Кладёт вычитанные комментарии. Возвращает число новых."""
    from datetime import datetime

    c = conn.cursor()
    names = _names(response)
    community = f"-{str(vk_group_id).lstrip('-')}"
    new = 0

    for item in _flatten(response):
        external_id = str(item.get("id"))
        author = str(item.get("from_id", ""))
        # Отрицательный идентификатор автора у ВК означает сообщество. Наш ответ
        # — это комментарий от лица именно нашего сообщества, а не любого.
        from_group = author == community
        created = datetime.fromtimestamp(item.get("date", 0), tz=UTC)
        parent = item.get("reply_to_comment")

        c.execute(
            "INSERT INTO post_comments (post_id, group_id, platform, external_id, "
            "  parent_external_id, author_external_id, author_name, text, created_at, "
            "  from_group, warned_at) "
            "VALUES (%(post_id)s, %(gid)s, 'vk', %(external_id)s, %(parent)s, %(author)s, "
            "        %(name)s, %(text)s, %(created)s, %(from_group)s, %(warned)s) "
            # Текст комментария в ВК можно поправить, поэтому обновляем — но
            # только его: остальное неизменно, а answered_at трогать нельзя,
            # иначе повторное вычитывание сбрасывало бы отметку об ответе.
            "ON CONFLICT (post_id, platform, external_id) DO UPDATE SET text = EXCLUDED.text "
            "RETURNING (xmax = 0) AS inserted",
            {"post_id": post["id"], "gid": gid, "external_id": external_id,
             "parent": str(parent) if parent else None, "author": author,
             "name": names.get(author, "Пользователь"), "text": item.get("text") or "",
             "created": created, "from_group": from_group,
             # На первом проходе отметку о предупреждении ставим сразу: это
             # история, а не событие, и уведомлять о ней некого и незачем.
             "warned": app_now() if first_pass else None},
        )
        row = c.fetchone()
        if row and row["inserted"]:
            new += 1
    return new


def resolve_answers(conn, post_id: int) -> int:
    """
    Проставляет отметку об ответе. Возвращает число закрытых обращений.

    Адресный ответ закрывает своё обращение. Ответ без адресата закрывает всё,
    что было до него под этой записью, — так отвечают, когда вопрос один.
    """
    c = conn.cursor()
    c.execute(
        "SELECT external_id, parent_external_id, created_at, from_group "
        "FROM post_comments WHERE post_id=%s ORDER BY created_at, id",
        (post_id,),
    )
    rows = [dict(r) for r in c.fetchall()]
    replies = [r for r in rows if r["from_group"]]
    if not replies:
        return 0

    answered: dict[str, object] = {}
    for reply in replies:
        if reply["parent_external_id"]:
            answered.setdefault(reply["parent_external_id"], reply["created_at"])
            continue
        for row in rows:
            if row["from_group"] or row["created_at"] > reply["created_at"]:
                continue
            answered.setdefault(row["external_id"], reply["created_at"])

    closed = 0
    for external_id, at in answered.items():
        c.execute(
            "UPDATE post_comments SET answered_at=%s "
            "WHERE post_id=%s AND external_id=%s AND from_group=false AND answered_at IS NULL",
            (at, post_id, external_id),
        )
        closed += c.rowcount
    return closed


def deadline(created_at, sla_hours: int):
    """Момент, к которому обращение должно быть отвечено."""
    return parse_dt(created_at) + timedelta(hours=sla_hours)


def _warn_about_deadlines(conn, group: dict) -> int:
    """
    Предупреждает администраторов группы о том, что срок вот-вот выйдет.

    Предупреждать в момент наступления срока бессмысленно: он уже вышел.
    Поэтому за четверть срока до него, и один раз на обращение — иначе
    напоминание приходило бы каждые десять минут и его перестали бы читать.
    """
    sla = group.get("reply_sla_hours") or 8
    threshold = app_now() - timedelta(hours=sla * WARN_AT)
    c = conn.cursor()
    c.execute(
        "SELECT id, author_name, text FROM post_comments "
        "WHERE group_id=%s AND from_group=false AND answered_at IS NULL "
        "  AND warned_at IS NULL AND created_at <= %s "
        "ORDER BY created_at LIMIT 20",
        (group["id"], threshold),
    )
    pending = c.fetchall()
    if not pending:
        return 0

    c.execute("SELECT user_id FROM group_members WHERE group_id=%s AND role='admin'",
              (group["id"],))
    admins = [r["user_id"] for r in c.fetchall()]

    for row in pending:
        excerpt = (row["text"] or "").strip().replace("\n", " ")
        if len(excerpt) > 80:
            excerpt = excerpt[:80] + "…"
        for admin_id in admins:
            c.execute(
                "INSERT INTO notifications (user_id, message, type, is_read, group_id) "
                "VALUES (%s, %s, 'comment_due', 0, %s)",
                (admin_id,
                 f"Скоро истечёт срок ответа на комментарий от {row['author_name']}"
                 + (f": «{excerpt}»" if excerpt else ""),
                 group["id"]),
            )
        c.execute("UPDATE post_comments SET warned_at=%s WHERE id=%s", (app_now(), row["id"]))
    return len(pending)


def collect() -> int:
    """Один такт: вычитать комментарии, разметить ответы, предупредить о сроках."""
    if not COMMENTS_ENABLED:
        return 0
    conn = get_db()
    total_new = 0
    try:
        for group in _connected_groups(conn):
            first_pass = _first_pass(conn, group["id"])
            if first_pass:
                log.info(f"💬  первое вычитывание группы «{group['name']}»: "
                         "историю кладём молча, без уведомлений")
            for post in _recent_posts(conn, group["id"]):
                try:
                    response = vk_get_comments(
                        group["access_token"], group["vk_group_id"], post["vk_post_id"])
                except Exception as e:
                    # Пост могли удалить со стены, комментарии — закрыть.
                    # Это не повод бросать обход остальных.
                    log.warning(f"комментарии поста #{post['id']} не прочитаны: {e}")
                    continue
                total_new += _store(conn, post, group["id"], group["vk_group_id"],
                                    response, first_pass)
                resolve_answers(conn, post["id"])
                conn.commit()
            _warn_about_deadlines(conn, group)
            conn.commit()
    finally:
        conn.close()
    health.beat("comments")
    if total_new:
        log.info(f"💬  новых комментариев: {total_new}")
    return total_new


def stats(conn, gid: int, since=None, until=None) -> dict:
    """
    Сводка по обращениям — для отчёта учредителю.

    Считает только обращения граждан: наши ответы в знаменателе означали бы,
    что учреждение отвечает само себе.
    """
    c = conn.cursor()
    where = "group_id=%s AND from_group=false"
    params: list = [gid]
    if since:
        where += " AND created_at >= %s"
        params.append(since)
    if until:
        where += " AND created_at < %s"
        params.append(until)

    c.execute(
        f"SELECT COUNT(*) total, COUNT(answered_at) answered, "  # noqa: S608 — условие своё
        f"       AVG(EXTRACT(EPOCH FROM (answered_at - created_at))) avg_seconds "
        f"FROM post_comments WHERE {where}",
        params,
    )
    row = c.fetchone()
    total, answered = row["total"] or 0, row["answered"] or 0
    return {
        "total": total,
        "answered": answered,
        "pending": total - answered,
        # None, а не ноль: «ни на что не отвечали» и «отвечали мгновенно» —
        # разные вещи, и ноль часов прочитался бы как вторая.
        "avg_reply_hours": (round(row["avg_seconds"] / 3600, 1)
                            if row["avg_seconds"] is not None else None),
    }
