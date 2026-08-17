
from fastapi import APIRouter, Depends, HTTPException, Request

import audit
import media_library
from utils import (
    as_json_list,
    get_current_user_id,
    get_db,
    like_pattern,
    media_for_storage,
    page_meta,
    paging,
    require_group_member,
    sign_media_list,
)

router = APIRouter()


@router.get("/api/groups/{gid}/volunteer-media")
def get_volunteer_media(
    gid: int,
    event: str | None = None,
    user_id_filter: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    q = "SELECT vm.*, u.name as user_name FROM volunteer_media vm JOIN users u ON vm.user_id=u.id WHERE vm.group_id=%s"
    params: list = [gid]
    if role == "volunteer":
        q += " AND vm.user_id=%s"
        params.append(user_id)
    if event:
        q += " AND vm.event_name ILIKE %s"
        params.append(like_pattern(event))
    if status:
        q += " AND vm.status=%s"
        params.append(status)
    if user_id_filter and role != "volunteer":
        q += " AND vm.user_id=%s"
        params.append(user_id_filter)
    # Считаем по тем же условиям, что и выбираем. Раньше счётчик брал всю
    # группу целиком: волонтёр видел свои три загрузки и подпись «из 120», а
    # пагинация рисовала шесть несуществующих страниц.
    count_q = q.replace(
        "SELECT vm.*, u.name as user_name FROM volunteer_media vm JOIN users u ON vm.user_id=u.id",
        "SELECT COUNT(*) FROM volunteer_media vm", 1,
    )
    count_params = list(params)

    limit, offset = paging(limit, offset)
    q += " ORDER BY vm.created_at DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    c.execute(q, params)
    rows = c.fetchall()
    c.execute(count_q, count_params)
    total = c.fetchone()["count"]
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["media"] = sign_media_list(as_json_list(d["media"]))
        result.append(d)
    return {"items": result, **page_meta(total, limit, offset)}


@router.get("/api/groups/{gid}/media-library")
def get_media_library(
    gid: int,
    q: str | None = None,
    type: str | None = None,
    source: str | None = None,
    limit: int = 60,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
):
    """
    Всё уже загруженное в группе: одобренные материалы волонтёров плюс файлы
    из прошлых постов. Наблюдателям не отдаём — медиатека нужна тому, кто пишет.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдателям медиатека недоступна")
        return media_library.browse(conn, gid, q=q, kind=type, source=source,
                                    limit=limit, offset=offset)
    finally:
        conn.close()


@router.post("/api/groups/{gid}/volunteer-media")
def create_volunteer_media(gid: int, body: dict, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role not in ("volunteer", "editor", "admin"):
        conn.close()
        raise HTTPException(403, "Недостаточно прав")
    event_name = body.get("event_name", "").strip()
    if not event_name:
        conn.close()
        raise HTTPException(400, "Укажите название мероприятия")
    media = body.get("media", [])
    if not media:
        conn.close()
        raise HTTPException(400, "Добавьте хотя бы один файл")
    c.execute(
        "INSERT INTO volunteer_media (user_id, group_id, event_name, media) "
        "VALUES (%(user_id)s, %(group_id)s, %(event_name)s, %(media)s) RETURNING id",
        {"user_id": user_id, "group_id": gid, "event_name": event_name,
         "media": media_for_storage(media)},
    )
    vid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT vm.*, u.name as user_name FROM volunteer_media vm JOIN users u ON vm.user_id=u.id WHERE vm.id=%s", (vid,))
    row = c.fetchone()
    conn.close()
    d = dict(row)
    d["media"] = sign_media_list(as_json_list(d["media"]))
    return d


@router.delete("/api/groups/{gid}/volunteer-media/{vid}")
def delete_volunteer_media(
    gid: int, vid: int,
    user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    c.execute(
        "SELECT user_id, event_name FROM volunteer_media WHERE id=%s AND group_id=%s", (vid, gid)
    )
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Медиа не найдено")
    if role == "volunteer" and row["user_id"] != user_id:
        conn.close()
        raise HTTPException(403, "Нельзя удалить чужую загрузку")
    c.execute("DELETE FROM volunteer_media WHERE id=%s", (vid,))
    audit.record(
        conn, user_id, audit.MEDIA_DELETED,
        object_type="volunteer_media", object_id=vid,
        object_label=row["event_name"], group_id=gid,
        details={"чужая загрузка": row["user_id"] != user_id}, request=request,
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/api/groups/{gid}/volunteer-media/{vid}/status")
def update_volunteer_media_status(gid: int, vid: int, body: dict, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role not in ("admin", "editor"):
        conn.close()
        raise HTTPException(403, "Только редактор или администратор может менять статус")
    new_status = body.get("status", "")
    if new_status not in ("approved", "rejected", "pending"):
        conn.close()
        raise HTTPException(400, "Некорректный статус. Допустимы: approved, rejected, pending")
    c.execute("UPDATE volunteer_media SET status=%s WHERE id=%s AND group_id=%s", (new_status, vid, gid))
    conn.commit()
    c.execute("SELECT vm.*, u.name as user_name FROM volunteer_media vm JOIN users u ON vm.user_id=u.id WHERE vm.id=%s", (vid,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Медиа не найдено")
    d = dict(row)
    d["media"] = sign_media_list(as_json_list(d["media"]))
    return d
