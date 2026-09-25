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
    ResetPasswordRequest,
)
from utils import (
    DEFAULT_SMTP_PORT,
    SMTP_SSL_PORT,
    check_invite_usable,
    check_rate_limit,
    client_ip,
    create_token,
    current_session,
    email_transport,
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
    verify_password,
)

router = APIRouter()
log = get_logger("auth")


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

    Проверяет ровно тот путь, которым уходят настоящие письма. Отдельная
    проверка «какого-нибудь SMTP» отвечала бы на вопрос, которого никто не
    задавал: раньше здесь стоял адрес Gmail по умолчанию, и ручка бодро
    рапортовала об успехе, пока письма уходили через Brevo и не уходили вовсе.
    """
    conn = get_db()
    try:
        require_admin(actor_id, conn)
    finally:
        conn.close()

    transport = email_transport()
    if transport == "none":
        return {"ok": False, "transport": transport,
                "error": "Отправка писем не настроена"}
    if transport == "brevo":
        return {"ok": False, "transport": transport,
                "error": "Письма идут через Brevo — эта проверка только для SMTP"}

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "").strip() or DEFAULT_SMTP_PORT)
    except ValueError:
        return {"ok": False, "transport": transport, "error": "SMTP_PORT должен быть числом"}

    try:
        if smtp_port == SMTP_SSL_PORT:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(smtp_user, smtp_password)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
        return {"ok": True, "transport": transport,
                "message": f"Связь с {smtp_host} есть, вход под {smtp_user} принят"}
    except Exception as e:
        log.warning(f"SMTP недоступен: {type(e).__name__}: {e}")
        return {"ok": False, "transport": transport,
                "error": f"Не удалось подключиться к SMTP: {type(e).__name__}"}


@router.post("/api/auth/register")
def register(req: RegisterRequest, request: Request = None):
    """
    Аккаунт создаётся сразу и человек сразу же пускается внутрь: почта
    не подтверждается кодом. Раньше регистрация была двухшаговой — заявка в
    email_verifications, код на почту, подтверждение через verify-email, — и
    на каждом шаге люди терялись: письма не доходили, код протухал.

    В чужую группу это по-прежнему не пускает: попасть туда можно только по
    действующему приглашению (см. test_registration_isolation.py).
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

    # Про мёртвое приглашение надо сказать сразу, ещё до создания аккаунта:
    # иначе человек зарегистрируется, а в группу не попадёт и не поймёт, за что.
    if req.invite_token:
        try:
            check_invite_usable(req.invite_token.strip(), conn)
        except HTTPException:
            conn.close()
            raise

    avatar = "".join(p[0].upper() for p in name.split()[:2])
    c.execute(
        "INSERT INTO users (name, email, role, avatar, password_hash) "
        "VALUES (%(name)s, %(email)s, %(role)s, %(avatar)s, %(password_hash)s) RETURNING id",
        {"name": name, "email": email, "role": "member", "avatar": avatar,
         "password_hash": hash_password(req.password)},
    )
    uid = c.fetchone()["id"]

    # Никакого автоматического вступления в группу. Раньше новый пользователь
    # молча попадал в первую группу (ORDER BY id ASC LIMIT 1) с ролью editor —
    # то есть любой посторонний после регистрации мог публиковать в реальные
    # VK-паблик и Telegram-канал организации. Приглашение, оказавшееся мёртвым
    # именно в этот момент, аккаунт не отменяет — но об этом честно говорим.
    invite_error = None
    if req.invite_token:
        try:
            redeem_invite(req.invite_token.strip(), uid, conn)
        except HTTPException as e:
            invite_error = e.detail
    session = _issue_session(c, uid, request)
    conn.close()
    return {**session, "invite_error": invite_error}


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
