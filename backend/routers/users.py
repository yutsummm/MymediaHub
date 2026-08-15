import re

from fastapi import APIRouter, Depends, HTTPException

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
def update_role(user_id: int, body: UserUpdate, actor_id: int = Depends(get_current_user_id)):
    if body.role not in GLOBAL_ROLES:
        raise HTTPException(400, f"Недопустимая роль. Допустимы: {', '.join(GLOBAL_ROLES)}")
    conn = get_db()
    c = conn.cursor()
    require_admin(actor_id, conn)
    if actor_id == user_id and body.role != "admin":
        conn.close()
        raise HTTPException(400, "Нельзя снять с себя права администратора")
    _guard_last_admin(c, conn, user_id, becoming=body.role)
    c.execute("UPDATE users SET role=%s WHERE id=%s", (body.role, user_id))
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
        "INSERT INTO users (name, email, role, avatar, password_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (body.name.strip(), body.email.lower().strip(), body.role, avatar, hash_password(body.password)),
    )
    uid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = c.fetchone()
    conn.close()
    return row_to_dict(user)


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, actor_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_admin(actor_id, conn)
    if actor_id == user_id:
        conn.close()
        raise HTTPException(400, "Нельзя удалить самого себя")
    _guard_last_admin(c, conn, user_id, becoming=None)
    c.execute("SELECT id FROM users WHERE id=%s", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Пользователь не найден")
    c.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
