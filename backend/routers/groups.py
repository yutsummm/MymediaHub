import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg2.extras import Json

import audit
import onboarding
import slots as publishing_slots
from models import (
    GroupCreate,
    GroupMemberRoleUpdate,
    GroupUpdate,
    InviteLinkCreate,
    SlotsUpdate,
)
from utils import (
    GROUP_ROLES,
    get_current_user_id,
    get_db,
    redeem_invite,
    require_group_member,
)

router = APIRouter()


@router.post("/api/groups")
def create_group(req: GroupCreate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO groups (name, description, created_by) VALUES (%s, %s, %s) RETURNING id",
        (req.name, req.description, user_id),
    )
    gid = c.fetchone()["id"]
    c.execute(
        "INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'admin')",
        (gid, user_id),
    )
    conn.commit()
    c.execute("SELECT id, name, description, avatar, require_approval, utm_enabled, variables, hashtag_sets, created_by, created_at FROM groups WHERE id=%s", (gid,))
    group = c.fetchone()
    conn.close()
    result = dict(group)
    result["role"] = "admin"
    return result


@router.get("/api/groups")
def get_my_groups(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT g.id, g.name, g.description, g.avatar, g.require_approval, g.utm_enabled, g.variables, g.hashtag_sets, gm.role, g.created_at "
        "FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id=%s ORDER BY g.id",
        (user_id,),
    )
    groups = [dict(r) for r in c.fetchall()]
    conn.close()
    return groups


@router.get("/api/groups/{gid}")
def get_group(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    c.execute("SELECT id, name, description, avatar, require_approval, utm_enabled, variables, hashtag_sets, created_by, created_at FROM groups WHERE id=%s", (gid,))
    group = c.fetchone()
    conn.close()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    result = dict(group)
    result["role"] = role
    return result


@router.get("/api/groups/{gid}/onboarding")
def get_onboarding(gid: int, user_id: int = Depends(get_current_user_id)):
    """
    Что в этой группе ещё не настроено.

    Считается по данным на каждый запрос: флаг «уже сделал» умеет разойтись с
    реальностью — интеграцию отключили, а галочка осталась.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        return onboarding.progress(conn, gid, role)
    finally:
        conn.close()


@router.get("/api/groups/{gid}/slots")
def get_slots(gid: int, user_id: int = Depends(get_current_user_id)):
    """Расписание публикаций группы: когда она обычно выкладывает посты."""
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        return {"slots": publishing_slots.list_slots(conn, gid)}
    finally:
        conn.close()


@router.put("/api/groups/{gid}/slots")
def update_slots(gid: int, req: SlotsUpdate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role != "admin":
            raise HTTPException(403, "Расписание публикаций меняет администратор группы")
        return {"slots": publishing_slots.replace_slots(
            conn, gid, [s.dict() for s in req.slots])}
    finally:
        conn.close()


@router.get("/api/groups/{gid}/slots/next")
def get_next_slot(gid: int, user_id: int = Depends(get_current_user_id)):
    """
    Ближайшее свободное окно — интерфейс показывает его до постановки в
    очередь, чтобы человек заранее видел, когда пост выйдет.
    """
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        from utils import fmt_dt
        return {"at": fmt_dt(publishing_slots.next_free_slot(conn, gid))}
    finally:
        conn.close()


@router.put("/api/groups/{gid}")
def update_group(gid: int, req: GroupUpdate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может изменять параметры группы")
    updates: list[str] = []
    params: list = []
    # variables и hashtag_sets — jsonb: без обёртки psycopg2 отправит dict как
    # строку его питоновского представления, и в колонке окажется мусор.
    JSON_COLUMNS = ("variables", "hashtag_sets")
    for field, value in req.dict(exclude_unset=True).items():
        updates.append(f"{field}=%s")
        params.append(Json(value) if field in JSON_COLUMNS else value)
    if not updates:
        conn.close()
        return get_group(gid, user_id)
    params.append(gid)
    c.execute(f"UPDATE groups SET {', '.join(updates)} WHERE id=%s", params)
    conn.commit()
    c.execute("SELECT id, name, description, avatar, require_approval, utm_enabled, variables, hashtag_sets, created_by, created_at FROM groups WHERE id=%s", (gid,))
    group = c.fetchone()
    conn.close()
    result = dict(group)
    result["role"] = role
    return result


@router.get("/api/groups/{gid}/deletion-preview")
def group_deletion_preview(gid: int, user_id: int = Depends(get_current_user_id)):
    """
    Что именно исчезнет вместе с группой.

    Интерфейс спрашивал «Удалить группу?», а исчезал год работы: посты,
    приглашения, медиа волонтёров, подключённые паблики. Человек должен видеть
    смету до того, как согласится.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role != "admin":
            raise HTTPException(403, "Только администратор может удалять группу")
        preview = audit.group_deletion_preview(conn, gid)
    finally:
        conn.close()
    if not preview:
        raise HTTPException(404, "Группа не найдена")
    return preview


@router.delete("/api/groups/{gid}")
def delete_group(
    gid: int,
    confirm: str = Query(None, description="Точное название группы"),
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """
    Удаляет группу вместе со всем её содержимым.

    Требует подтверждения — точного названия группы. Набрать его осмысленно, а
    нажать «Да» — нет, и цена ошибки здесь несоразмерна: восстановить можно
    только из резервной копии базы.

    Само удаление до этой правки работало наполовину: участников и приглашения
    сносил CASCADE, а посты, уведомления и интеграции внешние ключи не пускали
    вовсе — запрос падал с ForeignKeyViolation, и группу с хотя бы одним постом
    удалить было физически нельзя. Правила приведены в порядок миграцией
    e3b7d2f81a45; содержимое уходит вместе с группой одной транзакцией.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role != "admin":
            raise HTTPException(403, "Только администратор может удалять группу")
        preview = audit.group_deletion_preview(conn, gid)
        if not preview:
            raise HTTPException(404, "Группа не найдена")
        if (confirm or "").strip() != preview["name"]:
            raise HTTPException(
                409,
                f"Удаление не подтверждено. Введите точное название группы: «{preview['name']}». "
                f"Вместе с ней исчезнут посты ({preview['posts']}), участники "
                f"({preview['members']}) и медиа волонтёров ({preview['volunteer_media']}).",
            )

        c = conn.cursor()
        # Запись в журнал — до удаления и в той же транзакции: после удаления
        # название и счётчики уже не у кого спросить.
        audit.record(
            conn, user_id, audit.GROUP_DELETED,
            object_type="group", object_id=gid, object_label=preview["name"],
            group_id=gid, details=preview, request=request,
        )
        c.execute("DELETE FROM groups WHERE id=%s", (gid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "deleted": preview}


@router.get("/api/groups/{gid}/members")
def get_group_members(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_group_member(gid, user_id, conn)
    c.execute(
        "SELECT u.id, u.name, u.email, u.avatar, gm.role, gm.joined_at "
        "FROM users u JOIN group_members gm ON u.id = gm.user_id WHERE gm.group_id=%s ORDER BY u.id",
        (gid,),
    )
    members = [dict(r) for r in c.fetchall()]
    conn.close()
    return members


@router.put("/api/groups/{gid}/members/{uid}/role")
def update_member_role(
    gid: int, uid: int, req: GroupMemberRoleUpdate,
    user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может изменять роли")
    # Роль внутри группы и глобальная роль — разные наборы значений. Без этой
    # проверки в group_members попадало бы что угодно, включая глобальное
    # «member», от которого не работает ни одна проверка прав.
    if req.role not in GROUP_ROLES:
        conn.close()
        raise HTTPException(400, f"Недопустимая роль в группе. Допустимы: {', '.join(GROUP_ROLES)}")
    if req.role != "admin" and uid == user_id:
        c.execute(
            "SELECT COUNT(*) n FROM group_members WHERE group_id=%s AND role='admin'", (gid,)
        )
        if c.fetchone()["n"] <= 1:
            conn.close()
            raise HTTPException(400, "Вы единственный администратор группы")
    c.execute("SELECT role FROM group_members WHERE group_id=%s AND user_id=%s", (gid, uid))
    was = c.fetchone()
    c.execute("UPDATE group_members SET role=%s WHERE group_id=%s AND user_id=%s", (req.role, gid, uid))
    audit.record(
        conn, user_id, audit.GROUP_MEMBER_ROLE_CHANGED,
        object_type="user", object_id=uid, group_id=gid,
        details={"было": was["role"] if was else None, "стало": req.role}, request=request,
    )
    conn.commit()
    c.execute(
        "SELECT u.id, u.name, u.email, u.avatar, gm.role, gm.joined_at "
        "FROM users u JOIN group_members gm ON u.id = gm.user_id WHERE gm.group_id=%s AND u.id=%s",
        (gid, uid),
    )
    member = c.fetchone()
    conn.close()
    return dict(member) if member else None


@router.delete("/api/groups/{gid}/members/{uid}")
def remove_group_member(
    gid: int, uid: int, user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin" and user_id != uid:
        conn.close()
        raise HTTPException(403, "Вы можете удалить только себя из группы")
    c.execute("SELECT name FROM users WHERE id=%s", (uid,))
    who = c.fetchone()
    c.execute("DELETE FROM group_members WHERE group_id=%s AND user_id=%s", (gid, uid))
    audit.record(
        conn, user_id, audit.GROUP_MEMBER_REMOVED,
        object_type="user", object_id=uid,
        object_label=who["name"] if who else None, group_id=gid,
        details={"сам себя": user_id == uid}, request=request,
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/groups/{gid}/invites")
def create_invite_link(gid: int, req: InviteLinkCreate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может создавать ссылки приглашения")
    if req.role not in GROUP_ROLES:
        conn.close()
        raise HTTPException(400, f"Недопустимая роль в группе. Допустимы: {', '.join(GROUP_ROLES)}")
    token = uuid.uuid4().hex
    # Колонка теперь timestamptz — строку с «Z» собирать незачем
    expires_at = datetime.now(UTC) + timedelta(hours=req.expires_hours)
    c.execute(
        "INSERT INTO invite_links (group_id, token, role, created_by, expires_at, max_uses) "
        "VALUES (%(group_id)s, %(token)s, %(role)s, %(created_by)s, %(expires_at)s, %(max_uses)s) "
        "RETURNING id",
        {"group_id": gid, "token": token, "role": req.role, "created_by": user_id,
         "expires_at": expires_at, "max_uses": req.max_uses},
    )
    link_id = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT id, token, role, expires_at, used_count, max_uses, created_at FROM invite_links WHERE id=%s", (link_id,))
    link = c.fetchone()
    conn.close()
    return dict(link)


@router.get("/api/groups/{gid}/invites")
def get_invite_links(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может просматривать ссылки приглашения")
    c.execute("SELECT id, token, role, expires_at, used_count, max_uses, created_at FROM invite_links WHERE group_id=%s ORDER BY id DESC", (gid,))
    links = [dict(r) for r in c.fetchall()]
    conn.close()
    return links


@router.delete("/api/groups/{gid}/invites/{link_id}")
def revoke_invite_link(
    gid: int, link_id: int, user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может отзывать ссылки")
    c.execute("DELETE FROM invite_links WHERE id=%s AND group_id=%s", (link_id, gid))
    audit.record(
        conn, user_id, audit.INVITE_REVOKED,
        object_type="invite", object_id=link_id, group_id=gid, request=request,
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/api/invites/{token}")
def get_invite_preview(token: str):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT il.group_id, g.name as group_name, g.description as group_description, "
        "il.role, il.expires_at FROM invite_links il JOIN groups g ON il.group_id = g.id WHERE il.token=%s",
        (token,),
    )
    link = c.fetchone()
    conn.close()
    if not link:
        raise HTTPException(404, "Ссылка приглашения не найдена")
    return dict(link)


@router.post("/api/invites/{token}/accept")
def accept_invite(token: str, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    try:
        gid = redeem_invite(token, user_id, conn)["group_id"]
    except HTTPException:
        conn.rollback()
        conn.close()
        raise
    conn.commit()
    c.execute(
        "SELECT g.id, g.name, g.description, g.avatar, g.require_approval, g.utm_enabled, g.variables, g.hashtag_sets, gm.role, g.created_at "
        "FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id=%s AND g.id=%s",
        (user_id, gid),
    )
    group = c.fetchone()
    conn.close()
    return dict(group) if group else {"ok": True}
