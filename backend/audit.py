"""
Журнал действий и предупреждение перед необратимым.

Удаление группы уносило участников, приглашения и медиа волонтёров — и не
оставляло от этого ничего. Ни записи, ни отметки, ни возможности спросить, кто
и когда это сделал: содержимое просто переставало существовать. Даже сам
удаляющий не знал заранее, что именно исчезнет, — интерфейс спрашивал
«Удалить группу?», а исчезал год работы.

Отсюда два механизма.

**Смета.** Перед удалением считаем, что именно уйдёт (`group_deletion_preview`,
`user_deletion_preview`), и показываем это человеку. Удаление принимается
только с подтверждением — точным названием группы или почтой пользователя.
Опечатка в диалоге не должна стоить архива: набрать название своей группы
осмысленно, а нажать «Да» — нет.

**Запись.** Всё необратимое пишется в `audit_log`: кто, что, когда, с какого
адреса и сколько чего унесло с собой. Отменить удаление это не позволяет —
восстановление лежит в резервных копиях базы, — но отвечает на вопрос «куда
делось», который до сих пор было некому задать.
"""
from psycopg2.extras import Json

from logs import get_logger
from utils import client_ip

log = get_logger("audit")

# Значения `action`. Строки свободные, но перечисление здесь — чтобы в журнале
# не завелось три написания одного и того же.
GROUP_DELETED = "group.deleted"
GROUP_MEMBER_REMOVED = "group.member_removed"
GROUP_MEMBER_ROLE_CHANGED = "group.member_role_changed"
INVITE_REVOKED = "group.invite_revoked"
USER_DELETED = "user.deleted"
USER_ROLE_CHANGED = "user.role_changed"
POST_DELETED = "post.deleted"
MEDIA_DELETED = "volunteer_media.deleted"
INTEGRATION_DISCONNECTED = "integration.disconnected"


def record(
    conn,
    actor_id: int | None,
    action: str,
    *,
    object_type: str | None = None,
    object_id: int | None = None,
    object_label: str | None = None,
    group_id: int | None = None,
    details: dict | None = None,
    request=None,
) -> None:
    """
    Пишет строку журнала. Коммит остаётся за вызывающим — запись обязана
    попасть в ту же транзакцию, что и само действие: иначе журнал разойдётся
    с реальностью в обе стороны (запись без удаления и удаление без записи).

    Ошибку журналирования наружу не выпускаем: не записанное удаление — беда,
    но отменять из-за этого уже выполненную операцию хуже.
    """
    try:
        c = conn.cursor()
        actor_email = None
        if actor_id is not None:
            c.execute("SELECT email FROM users WHERE id=%s", (actor_id,))
            row = c.fetchone()
            actor_email = row["email"] if row else None
        c.execute(
            "INSERT INTO audit_log (actor_id, actor_email, action, object_type, object_id, "
            "object_label, group_id, details, ip) VALUES (%(actor_id)s, %(actor_email)s, "
            "%(action)s, %(object_type)s, %(object_id)s, %(object_label)s, %(group_id)s, "
            "%(details)s, %(ip)s)",
            {
                "actor_id": actor_id,
                "actor_email": actor_email,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "object_label": object_label,
                "group_id": group_id,
                "details": Json(details) if details else None,
                "ip": client_ip(request) if request is not None else None,
            },
        )
    except Exception:
        log.exception(f"не удалось записать в журнал действие {action}")


# ── Смета удаления ───────────────────────────────────────────────────────────

def group_deletion_preview(conn, gid: int) -> dict:
    """Что именно исчезнет вместе с группой."""
    c = conn.cursor()
    c.execute("SELECT name FROM groups WHERE id=%s", (gid,))
    row = c.fetchone()
    if not row:
        return {}
    counts = {}
    for key, sql in (
        ("posts", "SELECT COUNT(*) n FROM posts WHERE group_id=%s"),
        ("published_posts",
         "SELECT COUNT(*) n FROM posts WHERE group_id=%s AND status='published'"),
        ("members", "SELECT COUNT(*) n FROM group_members WHERE group_id=%s"),
        ("invites", "SELECT COUNT(*) n FROM invite_links WHERE group_id=%s"),
        ("volunteer_media", "SELECT COUNT(*) n FROM volunteer_media WHERE group_id=%s"),
        ("notifications", "SELECT COUNT(*) n FROM notifications WHERE group_id=%s"),
    ):
        c.execute(sql, (gid,))
        counts[key] = c.fetchone()["n"]

    c.execute(
        "SELECT (SELECT COUNT(*) FROM vk_settings WHERE workspace_id=%s) "
        "     + (SELECT COUNT(*) FROM tg_settings WHERE workspace_id=%s) AS n",
        (gid, gid),
    )
    counts["integrations"] = c.fetchone()["n"]
    return {"name": row["name"], "confirm_with": row["name"], **counts}


def user_deletion_preview(conn, user_id: int) -> dict:
    """
    Что будет с человеком и его следами.

    Посты не удаляются вместе с автором — у них просто пропадает автор.
    Удаление сотрудника не должно стирать работу организации.
    """
    c = conn.cursor()
    c.execute("SELECT name, email FROM users WHERE id=%s", (user_id,))
    row = c.fetchone()
    if not row:
        return {}
    counts = {}
    for key, sql in (
        ("posts_kept", "SELECT COUNT(*) n FROM posts WHERE author_id=%s"),
        ("groups", "SELECT COUNT(*) n FROM group_members WHERE user_id=%s"),
        ("volunteer_media", "SELECT COUNT(*) n FROM volunteer_media WHERE user_id=%s"),
        ("sessions", "SELECT COUNT(*) n FROM sessions WHERE user_id=%s AND revoked_at IS NULL"),
    ):
        c.execute(sql, (user_id,))
        counts[key] = c.fetchone()["n"]

    # Группы, где он единственный администратор: после удаления ими будет
    # некому управлять, и об этом надо сказать заранее.
    c.execute(
        "SELECT g.name FROM group_members gm JOIN groups g ON g.id = gm.group_id "
        "WHERE gm.user_id=%s AND gm.role='admin' AND NOT EXISTS ("
        "  SELECT 1 FROM group_members other WHERE other.group_id = gm.group_id "
        "  AND other.role='admin' AND other.user_id <> gm.user_id)",
        (user_id,),
    )
    counts["sole_admin_of"] = [r["name"] for r in c.fetchall()]
    return {"name": row["name"], "email": row["email"], "confirm_with": row["email"], **counts}
