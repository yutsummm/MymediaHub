"""
Чтение журнала действий.

Записи ведёт `audit.record` в тех же транзакциях, что и сами операции.
Здесь только выдача — списком, постранично, с фильтрами.

Кто может смотреть: журнал группы — её администратор (там видно только её
события), весь журнал целиком — глобальный администратор.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from utils import (
    fmt_dt,
    get_current_user_id,
    get_db,
    page_meta,
    paging,
    require_group_member,
)

router = APIRouter()


def _rows(conn, where: str, params: list, limit: int, offset: int) -> dict:
    c = conn.cursor()
    c.execute(
        "SELECT id, created_at, actor_id, actor_email, action, object_type, object_id, "  # noqa: S608 — where собирается из своих кусков
        f"       object_label, group_id, details, ip FROM audit_log WHERE {where} "
        "ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    items = []
    for row in c.fetchall():
        item = dict(row)
        item["created_at"] = fmt_dt(item["created_at"])
        items.append(item)
    c.execute(f"SELECT COUNT(*) AS n FROM audit_log WHERE {where}", params)  # noqa: S608
    return {"items": items, "total": c.fetchone()["n"]}


def _filters(action: str | None, object_type: str | None) -> tuple[list[str], list]:
    where, params = [], []
    if action:
        where.append("action = %s")
        params.append(action)
    if object_type:
        where.append("object_type = %s")
        params.append(object_type)
    return where, params


@router.get("/api/audit")
def get_audit_log(
    limit: int = 50,
    offset: int = 0,
    action: str = Query(None),
    object_type: str = Query(None),
    user_id: int = Depends(get_current_user_id),
):
    """Весь журнал. Только для глобального администратора."""
    from utils import require_admin

    conn = get_db()
    try:
        require_admin(user_id, conn)
        limit, offset = paging(limit, offset)
        where, params = _filters(action, object_type)
        result = _rows(conn, " AND ".join(where) or "TRUE", params, limit, offset)
    finally:
        conn.close()
    return {"items": result["items"], **page_meta(result["total"], limit, offset)}


@router.get("/api/groups/{gid}/audit")
def get_group_audit_log(
    gid: int,
    limit: int = 50,
    offset: int = 0,
    action: str = Query(None),
    object_type: str = Query(None),
    user_id: int = Depends(get_current_user_id),
):
    """Журнал одной группы — её администратору."""
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role != "admin":
            raise HTTPException(403, "Журнал доступен только администратору группы")
        limit, offset = paging(limit, offset)
        where, params = _filters(action, object_type)
        where.append("group_id = %s")
        params.append(gid)
        result = _rows(conn, " AND ".join(where), params, limit, offset)
    finally:
        conn.close()
    return {"items": result["items"], **page_meta(result["total"], limit, offset)}
