"""
Согласование постов: редактор готовит — администратор группы выпускает.

До этого редактор публиковал прямо в официальные каналы учреждения. Для
молодёжного центра это неверно по сути: у публикации от лица организации есть
ответственный, и он должен увидеть текст **до** того, как тот выйдет, а не
узнать о нём из ленты. Отменить запись в ВК и Telegram задним числом можно, но
прочитавшим её это уже не поможет.

Маршрут: `draft` → `on_review` → (`scheduled` | публикация) либо назад в
`draft` с замечанием.

**Куда уходит одобренный пост, не спрашиваем отдельно.** Намерение автора уже
записано в самом посте: стоит будущая `scheduled_at` — значит в расписание,
не стоит — значит сразу в очередь. Отдельная колонка «что хотел автор» была бы
вторым источником правды о том же самом и однажды разошлась бы с первым.

**Согласование включается на группу, а не на систему.** Там, где единственный
активный человек — редактор, обязательное согласование означало бы, что
публиковать некому вообще; группа встала бы молча. Поэтому
`groups.require_approval`: у новых групп включено, у заведённых раньше
выключено (см. миграцию c8b3f5d21a70).

**Администратор группы согласование не проходит.** Он и есть тот, кто
утверждает; заставлять его утверждать самого себя — обряд без содержания.
"""
import audit
from logs import get_logger
from publish_queue import enqueue
from utils import app_now, parse_dt

log = get_logger("review")

# Полный набор статусов поста. CHECK в базе на них нет сознательно (миграция
# c8b3f5d21a70 объясняет, почему), поэтому набор стережёт приложение.
POST_STATUSES = ("draft", "on_review", "scheduled", "published")

# Статусы, которые означают «пост уходит людям». Их-то согласование и закрывает.
RELEASING_STATUSES = ("scheduled", "published")


def group_requires_approval(conn, gid: int | None) -> bool:
    """
    Нужна ли в этой группе виза. Пост вне группы согласовывать не с кем —
    он принадлежит одному человеку, и визировать его было бы не у кого.
    """
    if gid is None:
        return False
    c = conn.cursor()
    c.execute("SELECT require_approval FROM groups WHERE id=%s", (gid,))
    row = c.fetchone()
    return bool(row and row["require_approval"])


def may_release(conn, gid: int | None, role: str | None) -> bool:
    """Может ли этот человек выпускать пост в свет без чужой визы."""
    if role == "admin":
        return True
    return not group_requires_approval(conn, gid)


def check_may_release(conn, gid: int | None, role: str | None, status: str | None) -> None:
    """
    Не даёт редактору выставить посту статус, означающий выход в свет.

    Проверка стоит на всех трёх путях сразу — создание, изменение и ручка
    публикации, — потому что каждый из них выпускает пост самостоятельно:
    `scheduled` подхватит планировщик, `published` уйдёт через очередь. Закрыть
    только кнопку «Опубликовать» значило бы оставить дверь рядом открытой.
    """
    from fastapi import HTTPException

    if status not in RELEASING_STATUSES:
        return
    if may_release(conn, gid, role):
        return
    raise HTTPException(
        403,
        "В этой группе посты выходят после согласования. "
        "Отправьте пост на согласование — администратор группы его выпустит.",
    )


def _notify(c, user_id: int | None, message: str, kind: str, gid: int | None = None) -> None:
    if user_id is None:
        return
    c.execute(
        "INSERT INTO notifications (user_id, message, type, is_read, group_id) "
        "VALUES (%s, %s, %s, 0, %s)",
        (user_id, message, kind, gid),
    )


def _group_admins(c, gid: int) -> list[int]:
    c.execute("SELECT user_id FROM group_members WHERE group_id=%s AND role='admin'", (gid,))
    return [r["user_id"] for r in c.fetchall()]


def submit(conn, post: dict, user_id: int, request=None) -> None:
    """Отправляет пост на согласование и зовёт администраторов группы смотреть."""
    from fastapi import HTTPException

    if post["status"] == "published":
        raise HTTPException(409, "Опубликованный пост согласовывать уже поздно")

    c = conn.cursor()
    c.execute(
        "UPDATE posts SET status='on_review', submitted_at=%s, "
        "reviewed_at=NULL, reviewed_by=NULL, review_comment=NULL WHERE id=%s",
        (app_now(), post["id"]),
    )
    gid = post.get("group_id")
    if gid is not None:
        for admin_id in _group_admins(c, gid):
            if admin_id != user_id:
                _notify(c, admin_id, f"Пост «{post['title']}» ждёт согласования",
                        "review_requested", gid)
    audit.record(
        conn, user_id, audit.POST_SUBMITTED,
        object_type="post", object_id=post["id"], object_label=post["title"],
        group_id=gid, request=request,
    )
    conn.commit()


def approve(conn, post: dict, user_id: int, request=None) -> dict:
    """
    Одобряет пост и выпускает его туда, куда он собирался.

    Возвращает {"status": ..., "job": задача публикации | None} — интерфейсу
    нужно знать, ждать ли результата отправки или пост просто встал в расписание.
    """
    from fastapi import HTTPException

    if post["status"] != "on_review":
        raise HTTPException(409, "Пост не на согласовании")

    c = conn.cursor()
    scheduled_at = parse_dt(post.get("scheduled_at"))
    to_schedule = scheduled_at is not None and scheduled_at > app_now()

    c.execute(
        "UPDATE posts SET status=%s, reviewed_at=%s, reviewed_by=%s, review_comment=NULL "
        "WHERE id=%s",
        ("scheduled" if to_schedule else "draft", app_now(), user_id, post["id"]),
    )
    gid = post.get("group_id")
    audit.record(
        conn, user_id, audit.POST_APPROVED,
        object_type="post", object_id=post["id"], object_label=post["title"],
        group_id=gid,
        details={"выпуск": "по расписанию" if to_schedule else "сразу"},
        request=request,
    )

    job = None
    if to_schedule:
        _notify(c, post.get("author_id"),
                f"Пост «{post['title']}» согласован и выйдет по расписанию",
                "review_approved", gid)
        conn.commit()
    else:
        _notify(c, post.get("author_id"),
                f"Пост «{post['title']}» согласован и отправляется в публикацию",
                "review_approved", gid)
        # Коммитим до постановки в очередь: воркер разбирает её из другого
        # соединения и не увидел бы пост, пока наша транзакция не закрыта.
        conn.commit()
        job = enqueue(conn, post["id"], gid, user_id)

    return {"status": "scheduled" if to_schedule else "publishing", "job": job}


def reject(conn, post: dict, user_id: int, comment: str, request=None) -> None:
    """Возвращает пост автору с замечанием."""
    from fastapi import HTTPException

    if post["status"] != "on_review":
        raise HTTPException(409, "Пост не на согласовании")
    comment = (comment or "").strip()
    if not comment:
        # Без причины возврат бесполезен: автор увидит «доработайте» и не
        # узнает, что именно не так.
        raise HTTPException(400, "Напишите, что нужно поправить")

    c = conn.cursor()
    c.execute(
        "UPDATE posts SET status='draft', reviewed_at=%s, reviewed_by=%s, review_comment=%s "
        "WHERE id=%s",
        (app_now(), user_id, comment, post["id"]),
    )
    gid = post.get("group_id")
    _notify(c, post.get("author_id"),
            f"Пост «{post['title']}» вернули на доработку: {comment}",
            "review_rejected", gid)
    audit.record(
        conn, user_id, audit.POST_REJECTED,
        object_type="post", object_id=post["id"], object_label=post["title"],
        group_id=gid, details={"замечание": comment}, request=request,
    )
    conn.commit()
