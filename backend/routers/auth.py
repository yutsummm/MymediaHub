import os
import random
import re
import smtplib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from logs import get_logger
from models import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResendCodeRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from utils import (
    check_invite_usable,
    check_rate_limit,
    client_ip,
    create_token,
    current_session,
    get_current_user_id,
    get_db,
    hash_password,
    list_sessions,
    redeem_invite,
    require_admin,
    revoke_session,
    revoke_user_sessions,
    row_to_dict,
    send_reset_email,
    send_verification_email,
    verify_password,
)

router = APIRouter()
log = get_logger("auth")

# Сколько живёт код подтверждения регистрации.
VERIFICATION_TTL = timedelta(minutes=15)


def _issue_session(c, uid: int, request=None) -> dict:
    """Ответ, который ждёт фронт после успешного входа: пользователь, токен, группы."""
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = c.fetchone()
    c.execute(
        "SELECT g.id, g.name, g.description, g.avatar, gm.role, g.created_at "
        "FROM groups g JOIN group_members gm ON g.id = gm.group_id WHERE gm.user_id=%s ORDER BY g.id",
        (uid,),
    )
    groups = [dict(r) for r in c.fetchall()]
    return {"user": row_to_dict(user), "token": create_token(uid, request, c.connection), "groups": groups}


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(400, "Пароль должен содержать минимум 8 символов")
    if not re.search(r'[a-zA-Zа-яА-Я]', password):
        raise HTTPException(400, "Пароль должен содержать хотя бы одну букву")
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]', password):
        raise HTTPException(400, "Пароль должен содержать хотя бы один спецсимвол")


def _send_code_or_drop(conn, email: str, code: str) -> None:
    """
    Письмо уходит после коммита заявки. Если отправка не удалась — заявку
    убираем, иначе человек застрянет с кодом, которого никогда не увидит.
    """
    try:
        send_verification_email(email, code)
    except Exception as e:
        c = conn.cursor()
        c.execute("DELETE FROM email_verifications WHERE email=%s", (email,))
        conn.commit()
        conn.close()
        if isinstance(e, ValueError):
            raise HTTPException(503, str(e))
        log.exception("не удалось отправить письмо с кодом", extra={"email": email})
        raise HTTPException(500, "Не удалось отправить письмо. Попробуйте позже.")


@router.post("/api/auth/login")
def login(req: LoginRequest, request: Request = None):
    ip = client_ip(request)
    check_rate_limit(f"login:{ip}", 5, 60)

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
    session = _issue_session(c, user["id"], request)
    conn.close()
    return session


@router.get("/api/debug/smtp-test")
def smtp_test(actor_id: int = Depends(get_current_user_id)):
    """
    Проверка связи с почтовым сервером.

    Закрыта авторизацией и не отдаёт наружу подробностей: раньше ручка была
    открыта всем и возвращала в теле ответа полный трейсбек — а это имена
    внутренних модулей, пути и адрес SMTP-сервера. Подробности уходят в лог,
    ответ остаётся односложным.
    """
    conn = get_db()
    try:
        require_admin(actor_id, conn)
    finally:
        conn.close()

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
        log.warning(f"SMTP недоступен: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"Не удалось подключиться к SMTP: {type(e).__name__}"}


@router.post("/api/auth/register")
def register(req: RegisterRequest, request: Request = None):
    """
    Шаг 1 из 2. Пользователь здесь НЕ создаётся — заявка кладётся в
    email_verifications, а на почту уходит код. Аккаунт появляется только после
    /api/auth/verify-email. Иначе любым чужим адресом можно было завести
    рабочий аккаунт: почта никак не проверялась.
    """
    ip = client_ip(request)
    check_rate_limit(f"register:{ip}", 3, 300)
    if not req.name.strip():
        raise HTTPException(400, "Введите имя")
    if not req.email.strip():
        raise HTTPException(400, "Введите email")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", req.email.strip()):
        raise HTTPException(400, "Некорректный email")
    _validate_password(req.password)
    email = req.email.lower().strip()
    name = req.name.strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=%s", (email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(409, "Пользователь с таким email уже существует")

    # Ссылку проверяем сразу, не расходуя: про мёртвое приглашение надо сказать
    # здесь, а не после того, как человек сходит за кодом в почту.
    if req.invite_token:
        try:
            check_invite_usable(req.invite_token.strip(), conn)
        except HTTPException:
            conn.close()
            raise

    # Пароль храним уже захешированным: заявка живёт в базе до подтверждения.
    code = str(random.randint(100000, 999999))
    c.execute("DELETE FROM email_verifications WHERE email=%s", (email,))
    c.execute(
        "INSERT INTO email_verifications (email, name, password_hash, code, expires_at, invite_token) "
        "VALUES (%(email)s, %(name)s, %(password_hash)s, %(code)s, %(expires_at)s, %(invite_token)s)",
        {
            "email": email,
            "name": name,
            "password_hash": hash_password(req.password),
            "code": code,
            "expires_at": datetime.now(UTC) + VERIFICATION_TTL,
            "invite_token": req.invite_token.strip() if req.invite_token else None,
        },
    )
    conn.commit()
    _send_code_or_drop(conn, email, code)
    conn.close()
    return {"status": "code_sent", "email": email}


@router.post("/api/auth/verify-email")
def verify_email(req: VerifyEmailRequest, request: Request = None):
    """Шаг 2 из 2: код сошёлся — создаём пользователя и сразу пускаем внутрь."""
    ip = client_ip(request)
    check_rate_limit(f"verify:{ip}", 10, 300)
    email = req.email.lower().strip()
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM email_verifications WHERE email=%s ORDER BY id DESC LIMIT 1", (email,)
    )
    pending = c.fetchone()
    if not pending:
        conn.close()
        raise HTTPException(400, "Заявка не найдена. Зарегистрируйтесь заново")
    if datetime.now(UTC) > pending["expires_at"]:
        c.execute("DELETE FROM email_verifications WHERE email=%s", (email,))
        conn.commit()
        conn.close()
        raise HTTPException(400, "Срок действия кода истёк. Зарегистрируйтесь заново")
    if pending["code"] != req.code.strip():
        conn.close()
        raise HTTPException(400, "Неверный код подтверждения")

    # Пока заявка ждала подтверждения, адрес могли занять.
    c.execute("SELECT id FROM users WHERE email=%s", (email,))
    if c.fetchone():
        c.execute("DELETE FROM email_verifications WHERE email=%s", (email,))
        conn.commit()
        conn.close()
        raise HTTPException(409, "Пользователь с таким email уже существует")

    name = pending["name"]
    avatar = "".join(p[0].upper() for p in name.split()[:2])
    c.execute(
        "INSERT INTO users (name, email, role, avatar, password_hash) "
        "VALUES (%(name)s, %(email)s, %(role)s, %(avatar)s, %(password_hash)s) RETURNING id",
        {"name": name, "email": email, "role": "member", "avatar": avatar,
         "password_hash": pending["password_hash"]},
    )
    uid = c.fetchone()["id"]

    # Никакого автоматического вступления в группу. Раньше новый пользователь
    # молча попадал в первую группу (ORDER BY id ASC LIMIT 1) с ролью editor —
    # то есть любой посторонний после регистрации мог публиковать в реальные
    # VK-паблик и Telegram-канал организации. Попасть в чужую группу теперь
    # можно только по действующему приглашению.
    invite_error = None
    if pending["invite_token"]:
        try:
            redeem_invite(pending["invite_token"], uid, conn)
        except HTTPException as e:
            # Приглашение могло истечь, пока человек искал письмо. Аккаунт всё
            # равно заслужен — создаём, но честно говорим, что в группу не ввели.
            invite_error = e.detail
    c.execute("DELETE FROM email_verifications WHERE email=%s", (email,))
    conn.commit()
    session = _issue_session(c, uid, request)
    conn.close()
    return {**session, "invite_error": invite_error}


@router.post("/api/auth/resend-code")
def resend_code(req: ResendCodeRequest, request: Request = None):
    """Новый код по той же заявке — письмо теряется чаще, чем хотелось бы."""
    ip = client_ip(request)
    check_rate_limit(f"resend:{ip}", 3, 300)
    email = req.email.lower().strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM email_verifications WHERE email=%s", (email,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(400, "Заявка не найдена. Зарегистрируйтесь заново")
    code = str(random.randint(100000, 999999))
    c.execute(
        "UPDATE email_verifications SET code=%s, expires_at=%s WHERE email=%s",
        (code, datetime.now(UTC) + VERIFICATION_TTL, email),
    )
    conn.commit()
    _send_code_or_drop(conn, email, code)
    conn.close()
    return {"status": "code_sent", "email": email}


@router.post("/api/auth/logout")
def logout(session: tuple = Depends(current_session)):
    """
    Настоящий выход: гасит токен на сервере.

    Раньше выход был только на клиенте — приложение забывало токен, а сам токен
    оставался действительным ещё до 72 часов.
    """
    _, jti = session
    revoke_session(jti, "выход")
    return {"status": "ok"}


@router.post("/api/auth/logout-all")
def logout_everywhere(session: tuple = Depends(current_session)):
    """Погасить все токены — если есть подозрение, что токен увели."""
    user_id, jti = session
    revoked = revoke_user_sessions(user_id, "выход на всех устройствах", except_jti=jti)
    return {"status": "ok", "sessions_revoked": revoked}


@router.get("/api/auth/sessions")
def my_sessions(session: tuple = Depends(current_session)):
    """Активные входы: человек должен видеть, откуда в его аккаунт заходят."""
    user_id, jti = session
    sessions = list_sessions(user_id)
    for item in sessions:
        item["current"] = item["jti"] == jti
        # Идентификатор наружу не отдаём: он равносилен ссылке на сессию
        item.pop("jti", None)
    return {"sessions": sessions}


@router.post("/api/auth/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request = None):
    ip = client_ip(request)
    check_rate_limit(f"forgot:{ip}", 3, 300)
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
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
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
    except Exception:
        log.exception("не удалось отправить письмо для сброса пароля")
        raise HTTPException(500, "Не удалось отправить письмо. Попробуйте позже.")
    return {"status": "code_sent"}


@router.post("/api/auth/reset-password")
def reset_password(req: ResetPasswordRequest, request: Request = None):
    ip = client_ip(request)
    check_rate_limit(f"reset:{ip}", 5, 300)
    _validate_password(req.new_password)
    email = req.email.lower().strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM password_resets WHERE email=%s ORDER BY id DESC LIMIT 1", (email,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(400, "Код не найден. Запросите сброс пароля заново")
    if datetime.now(UTC) > row["expires_at"]:
        c.execute("DELETE FROM password_resets WHERE email=%s", (email,))
        conn.commit()
        conn.close()
        raise HTTPException(400, "Срок действия кода истёк. Запросите сброс пароля заново")
    if row["code"] != req.code.strip():
        conn.close()
        raise HTTPException(400, "Неверный код подтверждения")
    c.execute(
        "UPDATE users SET password_hash=%s WHERE email=%s RETURNING id",
        (hash_password(req.new_password), email),
    )
    changed = c.fetchone()
    c.execute("DELETE FROM password_resets WHERE email=%s", (email,))
    conn.commit()
    # Смена пароля обязана гасить старые токены: иначе тот, кто увёл токен,
    # продолжит работать с аккаунтом, а человек будет думать, что защитился.
    revoked = revoke_user_sessions(changed["id"], "смена пароля", conn) if changed else 0
    conn.close()
    return {"status": "ok", "sessions_revoked": revoked}
