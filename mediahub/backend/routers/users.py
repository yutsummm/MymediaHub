from fastapi import APIRouter, HTTPException
from utils import get_db, row_to_dict, hash_password
from models import UserUpdate, UserCreate
import re

router = APIRouter()


@router.get("/api/users")
def get_users(limit: int = 100, offset: int = 0):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY id LIMIT %s OFFSET %s", (limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()["count"]
    conn.close()
    return {"users": [row_to_dict(r) for r in rows], "total": total}


@router.put("/api/users/{user_id}/role")
def update_role(user_id: int, body: UserUpdate):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET role=%s WHERE id=%s", (body.role, user_id))
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = c.fetchone()
    conn.close()
    return row_to_dict(user)


@router.post("/api/users")
def create_user(body: UserCreate):
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
def delete_user(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=%s", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Пользователь не найден")
    c.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
