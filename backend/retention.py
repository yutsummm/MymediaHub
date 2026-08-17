"""
Автоснятие постов: анонс прошедшего мероприятия не должен висеть в ленте.

У молодёжного центра большая часть публикаций — приглашения на конкретную
дату. Через неделю такой пост уже вреден: человек видит в ленте «приходите
17 мая», идёт и не находит ничего.

Что снимается и что остаётся. Из соцсети исчезает **запись**, у нас остаётся
**пост**: он был опубликован, набрал просмотры и обязан посчитаться в отчёте
за период. Стереть его у себя значило бы задним числом переписать историю
работы организации. Поэтому `removed_at` — отметка «из ленты убрали», а не
удаление.

Повторов при ошибке нет, как и у публикации, но по другой причине: снятие
как раз идемпотентно (уже удалённая запись — это успех), а вот бесконечно
долбиться в соцсеть из-за отозванного токена смысла нет. Ошибка пишется в
`remove_error`, и её видно в интерфейсе.
"""
from logs import get_logger
from utils import (
    app_now,
    as_json_list,
    decrypt_row_secret,
    get_db,
    tg_delete_messages,
    vk_wall_delete,
)

log = get_logger("retention")


def _due(conn) -> list[dict]:
    c = conn.cursor()
    c.execute(
        "SELECT id, title, group_id, vk_post_id, tg_message_ids "
        "FROM posts "
        "WHERE auto_delete_at IS NOT NULL AND removed_at IS NULL "
        "  AND status='published' AND auto_delete_at <= %s "
        "ORDER BY auto_delete_at LIMIT 20",
        (app_now(),),
    )
    return [dict(r) for r in c.fetchall()]


def _vk_settings(c, group_id):
    if group_id is None:
        c.execute("SELECT group_id, access_token FROM vk_settings WHERE id=1")
    else:
        c.execute("SELECT group_id, access_token FROM vk_settings WHERE workspace_id=%s",
                  (group_id,))
    return decrypt_row_secret(c.fetchone(), "access_token")


def _tg_settings(c, group_id):
    if group_id is None:
        c.execute("SELECT bot_token, chat_id FROM tg_settings WHERE id=1")
    else:
        c.execute("SELECT bot_token, chat_id FROM tg_settings WHERE workspace_id=%s",
                  (group_id,))
    return decrypt_row_secret(c.fetchone(), "bot_token")


def remove_post(conn, post: dict) -> list[str]:
    """
    Снимает запись со всех площадок, куда она уходила. Возвращает список ошибок.

    Площадки независимы: отвалившийся Telegram не повод оставить запись висеть
    во ВКонтакте.
    """
    c = conn.cursor()
    problems: list[str] = []

    if post.get("vk_post_id"):
        vk = _vk_settings(c, post.get("group_id"))
        if vk:
            try:
                vk_wall_delete(vk["access_token"], vk["group_id"], post["vk_post_id"])
            except Exception as e:
                problems.append(f"ВКонтакте: {e}")
        else:
            problems.append("ВКонтакте: интеграция отключена, запись снять нечем")

    message_ids = as_json_list(post.get("tg_message_ids"))
    if message_ids:
        tg = _tg_settings(c, post.get("group_id"))
        if tg:
            try:
                tg_delete_messages(tg["bot_token"], tg["chat_id"], message_ids)
            except Exception as e:
                problems.append(f"Telegram: {e}")
        else:
            problems.append("Telegram: интеграция отключена, сообщение снять нечем")

    return problems


def _notify(c, post: dict, message: str, kind: str) -> None:
    c.execute("SELECT author_id FROM posts WHERE id=%s", (post["id"],))
    row = c.fetchone()
    if not row or row["author_id"] is None:
        return
    c.execute(
        "INSERT INTO notifications (user_id, message, type, is_read, group_id) "
        "VALUES (%s, %s, %s, 0, %s)",
        (row["author_id"], message, kind, post.get("group_id")),
    )


def process_due(max_posts: int = 20) -> int:
    """Снимает всё, чему пора. Возвращает количество обработанных постов."""
    conn = get_db()
    done = 0
    try:
        for post in _due(conn)[:max_posts]:
            problems = remove_post(conn, post)
            c = conn.cursor()
            if problems:
                # removed_at не ставим: снятие не состоялось, и повторить его
                # на следующем такте — правильно, запись всё ещё висит.
                c.execute("UPDATE posts SET remove_error=%s WHERE id=%s",
                          ("; ".join(problems), post["id"]))
                _notify(c, post,
                        f"Не удалось снять пост «{post['title']}» с публикации: {problems[0]}",
                        "error")
                log.warning(f"⚠️   пост #{post['id']} не снят: {problems}")
            else:
                c.execute(
                    "UPDATE posts SET removed_at=%s, remove_error=NULL WHERE id=%s",
                    (app_now(), post["id"]),
                )
                _notify(c, post,
                        f"Пост «{post['title']}» снят с публикации по расписанию", "info")
                done += 1
            conn.commit()
    finally:
        conn.close()
    return done
