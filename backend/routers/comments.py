"""
Очередь обращений: что спросили под публикациями и сколько осталось ответить.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

import comments as comments_service
from models import CommentReply
from utils import (
    app_now,
    decrypt_row_secret,
    fmt_dt,
    get_current_user_id,
    get_db,
    like_pattern,
    page_meta,
    paging,
    require_group_member,
    vk_wall_create_comment,
)

router = APIRouter()


def _serialize(row: dict, sla_hours: int) -> dict:
    due = comments_service.deadline(row["created_at"], sla_hours)
    now = app_now()
    answered = row["answered_at"] is not None
    return {
        "id": row["id"],
        "post_id": row["post_id"],
        "post_title": row.get("post_title"),
        "platform": row["platform"],
        "author_name": row["author_name"],
        "text": row["text"],
        "created_at": fmt_dt(row["created_at"]),
        "answered_at": fmt_dt(row["answered_at"]),
        "due_at": fmt_dt(due),
        # Сколько осталось до срока. Отрицательное — просрочено. У отвеченных
        # смысла не имеет: срок к ним уже неприменим.
        "minutes_left": None if answered else round((due - now).total_seconds() / 60),
        "overdue": (not answered) and due < now,
    }


@router.get("/api/groups/{gid}/comments")
def list_comments(
    gid: int,
    status: str = Query("pending", pattern="^(pending|answered|all)$"),
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
):
    """
    Обращения под публикациями группы.

    По умолчанию — только неотвеченные: очередь существует ради них, и
    открывать её на всём архиве значит прятать работу за историей.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдателям обращения недоступны")
        c = conn.cursor()
        c.execute("SELECT reply_sla_hours FROM groups WHERE id=%s", (gid,))
        row = c.fetchone()
        sla = (row["reply_sla_hours"] if row else 8) or 8

        # Наши собственные ответы в очередь не попадают: отвечать на них некому.
        where = "pc.group_id=%s AND pc.from_group=false"
        params: list = [gid]
        if status == "pending":
            where += " AND pc.answered_at IS NULL"
        elif status == "answered":
            where += " AND pc.answered_at IS NOT NULL"
        if q:
            where += " AND (pc.text ILIKE %s OR pc.author_name ILIKE %s)"
            pattern = like_pattern(q)
            params += [pattern, pattern]

        c.execute(f"SELECT COUNT(*) FROM post_comments pc WHERE {where}", params)  # noqa: S608
        total = c.fetchone()["count"]

        limit, offset = paging(limit, offset)
        c.execute(
            f"SELECT pc.*, p.title AS post_title FROM post_comments pc "  # noqa: S608
            f"JOIN posts p ON p.id = pc.post_id WHERE {where} "
            # Самые давние сверху: у них срок ближе всего.
            "ORDER BY pc.created_at LIMIT %s OFFSET %s",
            params + [limit, offset],
        )
        items = [_serialize(dict(r), sla) for r in c.fetchall()]
        return {"items": items, "sla_hours": sla, **page_meta(total, limit, offset)}
    finally:
        conn.close()


@router.get("/api/groups/{gid}/comments/summary")
def comments_summary(gid: int, user_id: int = Depends(get_current_user_id)):
    """Короткая сводка для значка в меню и для дашборда."""
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдателям обращения недоступны")
        c = conn.cursor()
        c.execute("SELECT reply_sla_hours FROM groups WHERE id=%s", (gid,))
        row = c.fetchone()
        sla = (row["reply_sla_hours"] if row else 8) or 8
        c.execute(
            "SELECT COUNT(*) AS pending, "
            "       COUNT(*) FILTER (WHERE created_at < %s) AS overdue "
            "FROM post_comments "
            "WHERE group_id=%s AND from_group=false AND answered_at IS NULL",
            (app_now() - timedelta(hours=sla), gid),
        )
        counts = dict(c.fetchone())
        return {"pending": counts["pending"], "overdue": counts["overdue"], "sla_hours": sla}
    finally:
        conn.close()


@router.post("/api/groups/{gid}/comments/{comment_id}/reply")
def reply_to_comment(
    gid: int, comment_id: int, body: CommentReply,
    user_id: int = Depends(get_current_user_id),
):
    """
    Отвечает на обращение от лица сообщества, не выходя из системы.

    Отметку об ответе ставим здесь же, а не ждём следующего вычитывания: между
    тактами до десяти минут, и всё это время отвеченное обращение висело бы в
    очереди — человек бы решил, что ответ не ушёл, и написал второй раз.
    """
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустой ответ отправить нельзя")

    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдатели не могут отвечать на обращения")
        c = conn.cursor()
        c.execute(
            "SELECT pc.*, p.vk_post_id FROM post_comments pc "
            "JOIN posts p ON p.id = pc.post_id "
            "WHERE pc.id=%s AND pc.group_id=%s",
            (comment_id, gid),
        )
        comment = c.fetchone()
        if not comment:
            raise HTTPException(404, "Обращение не найдено")
        if comment["answered_at"]:
            raise HTTPException(409, "На это обращение уже отвечено")
        if comment["platform"] != "vk":
            raise HTTPException(400, "Отвечать пока умеем только во ВКонтакте")

        c.execute("SELECT group_id, access_token FROM vk_settings WHERE workspace_id=%s", (gid,))
        vk = decrypt_row_secret(c.fetchone(), "access_token")
        if not vk:
            raise HTTPException(409, "ВКонтакте не подключён — отвечать нечем")

        try:
            vk_wall_create_comment(
                vk["access_token"], vk["group_id"], comment["vk_post_id"], text,
                reply_to_comment=comment["external_id"],
            )
        except Exception as e:
            raise HTTPException(502, f"ВКонтакте не принял ответ: {e}")

        c.execute(
            "UPDATE post_comments SET answered_at=%s, answered_by=%s WHERE id=%s",
            (app_now(), user_id, comment_id),
        )
        conn.commit()
        return {"ok": True, "answered_at": fmt_dt(app_now())}
    finally:
        conn.close()
