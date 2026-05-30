from fastapi import APIRouter, HTTPException, Request
from utils import (
    get_db, row_to_dict, hash_password, verify_password,
    create_token, get_current_user_id, check_rate_limit, send_reset_email,
)
from models import LoginRequest, RegisterRequest, ForgotPasswordRequest, ResetPasswordRequest
import random, datetime, re, os, smtplib, traceback, sys

router = APIRouter()


@router.post("/api/auth/login")
def login(req: LoginRequest, request: Request = None):
    client_ip = request.client.host if request else "unknown"
    check_rate_limit(f"login:{client_ip}", 5, 60)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=%s", (req.email,))
    user = c.fetchone()
    if not user:
        conn.close()
        raise HTTPException(401, "Пользователь не найден")
    ph = user.get("password_hash")
    if not ph or not verify_password(req.password, ph):
        conn.close()
        raise HTTPException(401, "Неверный пароль")
    user_id = user["id"]
    token = create_token(user_id)
    c.execute(
        "SELECT g.id, g.name, g.description, g.avatar, gm.role, g.created_at "
        "FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id=%s ORDER BY g.id",
        (user_id,),
    )
    groups = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"user": row_to_dict(user), "token": token, "groups": groups}


@router.get("/api/debug/smtp-test")
def smtp_test():
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_password:
        return {"ok": False, "error": "SMTP_USER или SMTP_PASSWORD не заданы"}
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
        return {"ok": True, "message": f"SMTP подключение успешно ({smtp_user})"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}


@router.post("/api/auth/register")
def register(req: RegisterRequest, request: Request = None):
    client_ip = request.client.host if request else "unknown"
    check_rate_limit(f"register:{client_ip}", 3, 300)
    if not req.name.strip():
        raise HTTPException(400, "Введите имя")
    if not req.email.strip():
        raise HTTPException(400, "Введите email")
    if len(req.password) < 8:
        raise HTTPException(400, "Пароль должен содержать минимум 8 символов")
    if not re.search(r'[a-zA-Zа-яА-Я]', req.password):
        raise HTTPException(400, "Пароль должен содержать хотя бы одну букву")
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]', req.password):
        raise HTTPException(400, "Пароль должен содержать хотя бы один спецсимвол")
    email = req.email.lower().strip()
    name = req.name.strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=%s", (email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(409, "Пользователь с таким email уже существует")
    avatar = "".join(p[0].upper() for p in name.split()[:2])
    c.execute(
        "INSERT INTO users (name, email, role, avatar, password_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (name, email, "editor", avatar, hash_password(req.password)),
    )
    uid = c.fetchone()["id"]
    c.execute("SELECT id FROM groups ORDER BY id ASC LIMIT 1")
    default_group = c.fetchone()
    if default_group:
        c.execute(
            "INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'editor') ON CONFLICT DO NOTHING",
            (default_group["id"], uid),
        )
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = c.fetchone()
    token = create_token(uid)
    c.execute(
        "SELECT g.id, g.name, g.description, g.avatar, gm.role, g.created_at "
        "FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id=%s ORDER BY g.id",
        (uid,),
    )
    groups = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"user": row_to_dict(user), "token": token, "groups": groups}


@router.post("/api/auth/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request = None):
    client_ip = request.client.host if request else "unknown"
    check_rate_limit(f"forgot:{client_ip}", 3, 300)
    email = req.email.lower().strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=%s", (email,))
    user = c.fetchone()
    if not user:
        conn.close()
        return {"status": "code_sent"}
    c.execute("DELETE FROM password_resets WHERE email=%s", (email,))
    code = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    c.execute(
        "INSERT INTO password_resets (email, code, expires_at) VALUES (%s, %s, %s)",
        (email, code, expires_at),
    )
    conn.commit()
    conn.close()
    try:
        send_reset_email(email, code)
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(500, f"Не удалось отправить письмо: {type(e).__name__}: {e}")
    return {"status": "code_sent"}


@router.post("/api/auth/reset-password")
def reset_password(req: ResetPasswordRequest, request: Request = None):
    client_ip = request.client.host if request else "unknown"
    check_rate_limit(f"reset:{client_ip}", 5, 300)
    if len(req.new_password) < 8:
        raise HTTPException(400, "Пароль должен содержать минимум 8 символов")
    if not re.search(r'[a-zA-Zа-яА-Я]', req.new_password):
        raise HTTPException(400, "Пароль должен содержать хотя бы одну букву")
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]', req.new_password):
        raise HTTPException(400, "Пароль должен содержать хотя бы один спецсимвол")
    email = req.email.lower().strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM password_resets WHERE email=%s ORDER BY id DESC LIMIT 1", (email,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(400, "Код не найден. Запросите сброс пароля заново")
    if datetime.utcnow() > row["expires_at"]:
        c.execute("DELETE FROM password_resets WHERE email=%s", (email,))
        conn.commit()
        conn.close()
        raise HTTPException(400, "Срок действия кода истёк. Запросите сброс пароля заново")
    if row["code"] != req.code.strip():
        conn.close()
        raise HTTPException(400, "Неверный код подтверждения")
    c.execute(
        "UPDATE users SET password_hash=%s WHERE email=%s",
        (hash_password(req.new_password), email),
    )
    c.execute("DELETE FROM password_resets WHERE email=%s", (email,))
    conn.commit()
    conn.close()
    return {"status": "ok"}
