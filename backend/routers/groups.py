import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from models import GroupCreate, GroupMemberRoleUpdate, GroupUpdate, InviteLinkCreate
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
    c.execute("SELECT id, name, description, avatar, created_by, created_at FROM groups WHERE id=%s", (gid,))
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
        "SELECT g.id, g.name, g.description, g.avatar, gm.role, g.created_at "
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
    c.execute("SELECT id, name, description, avatar, created_by, created_at FROM groups WHERE id=%s", (gid,))
    group = c.fetchone()
    conn.close()
    if not group:
        raise HTTPException(404, "Группа не найдена")
    result = dict(group)
    result["role"] = role
    return result


@router.put("/api/groups/{gid}")
def update_group(gid: int, req: GroupUpdate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может изменять параметры группы")
    updates = []
    params = []
    for field, value in req.dict(exclude_unset=True).items():
        updates.append(f"{field}=%s")
        params.append(value)
    if not updates:
        conn.close()
        return get_group(gid, user_id)
    params.append(gid)
    c.execute(f"UPDATE groups SET {', '.join(updates)} WHERE id=%s", params)
    conn.commit()
    c.execute("SELECT id, name, description, avatar, created_by, created_at FROM groups WHERE id=%s", (gid,))
    group = c.fetchone()
    conn.close()
    result = dict(group)
    result["role"] = role
    return result


@router.delete("/api/groups/{gid}")
def delete_group(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может удалять группу")
    c.execute("DELETE FROM groups WHERE id=%s", (gid,))
    conn.commit()
    conn.close()
    return {"ok": True}


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
def update_member_role(gid: int, uid: int, req: GroupMemberRoleUpdate, user_id: int = Depends(get_current_user_id)):
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
    c.execute("UPDATE group_members SET role=%s WHERE group_id=%s AND user_id=%s", (req.role, gid, uid))
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
def remove_group_member(gid: int, uid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin" and user_id != uid:
        conn.close()
        raise HTTPException(403, "Вы можете удалить только себя из группы")
    c.execute("DELETE FROM group_members WHERE group_id=%s AND user_id=%s", (gid, uid))
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
    expires_at = (datetime.utcnow() + timedelta(hours=req.expires_hours)).isoformat() + "Z"
    c.execute(
        "INSERT INTO invite_links (group_id, token, role, created_by, expires_at, max_uses) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (gid, token, req.role, user_id, expires_at, req.max_uses),
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
def revoke_invite_link(gid: int, link_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может отзывать ссылки")
    c.execute("DELETE FROM invite_links WHERE id=%s AND group_id=%s", (link_id, gid))
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
        "SELECT g.id, g.name, g.description, g.avatar, gm.role, g.created_at "
        "FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id=%s AND g.id=%s",
        (user_id, gid),
    )
    group = c.fetchone()
    conn.close()
    return dict(group) if group else {"ok": True}
