import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import audit
from models import UserCreate, UserUpdate
from utils import (
    GLOBAL_ROLES,
    get_current_user_id,
    get_db,
    hash_password,
    page_meta,
    paging,
    require_admin,
    row_to_dict,
)

router = APIRouter()


def _guard_last_admin(c, conn, target_id: int, becoming: str | None) -> None:
    """
    Не даёт остаться без администраторов.

    Проверка обязана быть здесь, а не в интерфейсе: список пользователей теперь
    постраничный, и «последний админ» по загруженной странице — это неправда.
    becoming=None означает удаление пользователя.
    """
    c.execute("SELECT role FROM users WHERE id=%s", (target_id,))
    row = c.fetchone()
    if not row or row["role"] != "admin" or becoming == "admin":
        return
    c.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin'")
    if c.fetchone()["n"] <= 1:
        conn.close()
        raise HTTPException(
            400,
            "Это единственный администратор. Сначала назначьте другого — иначе "
            "управлять пользователями станет некому.",
        )


@router.get("/api/users")
def get_users(limit: int = 100, offset: int = 0, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_admin(user_id, conn)
    limit, offset = paging(limit, offset)
    c.execute("SELECT * FROM users ORDER BY id LIMIT %s OFFSET %s", (limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()["count"]
    conn.close()
    return {"users": [row_to_dict(r) for r in rows], **page_meta(total, limit, offset)}


@router.put("/api/users/{user_id}/role")
def update_role(
    user_id: int, body: UserUpdate,
    actor_id: int = Depends(get_current_user_id), request: Request = None,
):
    if body.role not in GLOBAL_ROLES:
        raise HTTPException(400, f"Недопустимая роль. Допустимы: {', '.join(GLOBAL_ROLES)}")
    conn = get_db()
    c = conn.cursor()
    require_admin(actor_id, conn)
    if actor_id == user_id and body.role != "admin":
        conn.close()
        raise HTTPException(400, "Нельзя снять с себя права администратора")
    _guard_last_admin(c, conn, user_id, becoming=body.role)
    c.execute("SELECT role, email FROM users WHERE id=%s", (user_id,))
    was = c.fetchone()
    c.execute("UPDATE users SET role=%s WHERE id=%s", (body.role, user_id))
    # Глобальная роль admin — это доступ ко всем пользователям системы.
    # Её выдача обязана оставлять след.
    audit.record(
        conn, actor_id, audit.USER_ROLE_CHANGED,
        object_type="user", object_id=user_id,
        object_label=was["email"] if was else None,
        details={"было": was["role"] if was else None, "стало": body.role}, request=request,
    )
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = c.fetchone()
    conn.close()
    return row_to_dict(user)


@router.post("/api/users")
def create_user(body: UserCreate, actor_id: int = Depends(get_current_user_id)):
    if body.role not in GLOBAL_ROLES:
        raise HTTPException(400, f"Недопустимая роль. Допустимы: {', '.join(GLOBAL_ROLES)}")
    if not body.name.strip():
        raise HTTPException(400, "Введите имя")
    if not body.email.strip():
        raise HTTPException(400, "Введите email")
    if len(body.password) < 8:
        raise HTTPException(400, "Пароль должен содержать минимум 8 символов")
    if not re.search(r'[a-zA-Zа-яА-Я]', body.password):
        raise HTTPException(400, "Пароль должен содержать хотя бы одну букву")
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]', body.password):
        raise HTTPException(400, "Пароль должен содержать хотя бы один спецсимвол")
    conn = get_db()
    c = conn.cursor()
    require_admin(actor_id, conn)
    c.execute("SELECT id FROM users WHERE email=%s", (body.email.lower().strip(),))
    if c.fetchone():
        conn.close()
        raise HTTPException(409, "Пользователь с таким email уже существует")
    avatar = "".join(p[0].upper() for p in body.name.strip().split()[:2])
    c.execute(
        "INSERT INTO users (name, email, role, avatar, password_hash) "
        "VALUES (%(name)s, %(email)s, %(role)s, %(avatar)s, %(password_hash)s) RETURNING id",
        {"name": body.name.strip(), "email": body.email.lower().strip(), "role": body.role,
         "avatar": avatar, "password_hash": hash_password(body.password)},
    )
    uid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = c.fetchone()
    conn.close()
    return row_to_dict(user)


@router.get("/api/users/{user_id}/deletion-preview")
def user_deletion_preview(user_id: int, actor_id: int = Depends(get_current_user_id)):
    """Что будет с человеком и его следами. Посты остаются, автор пропадает."""
    conn = get_db()
    try:
        require_admin(actor_id, conn)
        preview = audit.user_deletion_preview(conn, user_id)
    finally:
        conn.close()
    if not preview:
        raise HTTPException(404, "Пользователь не найден")
    return preview


@router.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    confirm: str = Query(None, description="Точный email пользователя"),
    actor_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """
    Удаляет пользователя. Подтверждение — его точный адрес почты.

    Раньше запрос попросту падал пятисоткой на любом, кто написал хотя бы один
    пост или создал группу: внешние ключи не давали удалить строку, а ошибку
    никто не ловил. Теперь посты и группы остаются, у них пропадает автор
    (SET NULL, миграция e3b7d2f81a45) — работа организации не должна исчезать
    вместе с уволившимся сотрудником.
    """
    conn = get_db()
    try:
        require_admin(actor_id, conn)
        c = conn.cursor()
        if actor_id == user_id:
            raise HTTPException(400, "Нельзя удалить самого себя")
        preview = audit.user_deletion_preview(conn, user_id)
        if not preview:
            raise HTTPException(404, "Пользователь не найден")
        _guard_last_admin(c, conn, user_id, becoming=None)
        if (confirm or "").strip().lower() != preview["email"].lower():
            raise HTTPException(
                409,
                f"Удаление не подтверждено. Введите точный email: «{preview['email']}». "
                f"Постов сохранится: {preview['posts_kept']} (у них пропадёт автор), "
                f"групп покинет: {preview['groups']}.",
            )
        audit.record(
            conn, actor_id, audit.USER_DELETED,
            object_type="user", object_id=user_id, object_label=preview["email"],
            details=preview, request=request,
        )
        c.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "deleted": preview}
