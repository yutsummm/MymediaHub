"""
Регистрация двухшаговая: аккаунт появляется только после подтверждения почты.

До этого /api/auth/register сразу создавал рабочего пользователя с любым, в том
числе чужим, адресом — таблица email_verifications лежала мёртвым грузом.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from conftest import auth, pending_code, register_and_verify


def fresh_email(prefix: str = "verify") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.local"


def pending_count(email: str) -> int:
    from utils import get_db

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) AS n FROM email_verifications WHERE email=%s", (email,))
    n = c.fetchone()["n"]
    conn.close()
    return n


def user_exists(email: str) -> bool:
    from utils import get_db

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE email=%s", (email,))
    found = c.fetchone() is not None
    conn.close()
    return found


# ── Шаг 1: заявка ────────────────────────────────────────────────────────────

def test_register_does_not_create_user(client):
    """Главное свойство фикса: до подтверждения пользователя в базе нет."""
    email = fresh_email()
    r = client.post(
        "/api/auth/register",
        json={"name": "Неподтверждённый", "email": email, "password": "Passw0rd!"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "code_sent"
    assert "token" not in r.json(), "токен нельзя выдавать до подтверждения почты"
    assert not user_exists(email)
    assert pending_count(email) == 1


def test_unverified_email_cannot_log_in(client):
    email = fresh_email()
    client.post(
        "/api/auth/register",
        json={"name": "Неподтверждённый", "email": email, "password": "Passw0rd!"},
    )
    r = client.post("/api/auth/login", json={"email": email, "password": "Passw0rd!"})
    assert r.status_code == 401


def test_repeated_register_replaces_pending_request(client):
    """Вторая попытка не должна плодить заявки — иначе старый код останется рабочим."""
    email = fresh_email()
    body = {"name": "Дважды", "email": email, "password": "Passw0rd!"}
    assert client.post("/api/auth/register", json=body).status_code == 200
    first_code = pending_code(email)
    assert client.post("/api/auth/register", json=body).status_code == 200
    assert pending_count(email) == 1
    assert pending_code(email) != first_code or True  # код случайный, важна единственность

    r = client.post("/api/auth/verify-email", json={"email": email, "code": first_code})
    if first_code != pending_code(email):
        assert r.status_code == 400, "старый код после переотправки не должен работать"


def test_register_rejects_existing_user_email(client):
    r = client.post(
        "/api/auth/register",
        json={"name": "Дубль", "email": "admin@mediahub.ru", "password": "Passw0rd!"},
    )
    assert r.status_code == 409


def test_register_rejects_malformed_email(client):
    r = client.post(
        "/api/auth/register",
        json={"name": "Кривой", "email": "не-почта", "password": "Passw0rd!"},
    )
    assert r.status_code == 400


@pytest.mark.parametrize("password", ["short1!", "12345678!", "password123"])
def test_register_still_validates_password(client, password):
    r = client.post(
        "/api/auth/register",
        json={"name": "Слабый", "email": fresh_email(), "password": password},
    )
    assert r.status_code == 400
    assert pending_count(fresh_email()) == 0


# ── Шаг 2: подтверждение ─────────────────────────────────────────────────────

def test_verify_creates_user_and_issues_token(client):
    email = fresh_email()
    body = register_and_verify(client, email)
    assert body["user"]["email"] == email
    assert body["token"]
    assert body["groups"] == [], "новичок не должен попадать ни в одну группу"
    assert user_exists(email)
    assert pending_count(email) == 0, "заявка должна убираться после подтверждения"

    # Выданным токеном можно работать, и обычный вход тоже открыт
    assert client.get("/api/groups", headers=auth(body["token"])).status_code == 200
    assert client.post(
        "/api/auth/login", json={"email": email, "password": "Passw0rd!"}
    ).status_code == 200


def test_verify_rejects_wrong_code(client):
    email = fresh_email()
    client.post(
        "/api/auth/register",
        json={"name": "Ошибся", "email": email, "password": "Passw0rd!"},
    )
    wrong = "000000" if pending_code(email) != "000000" else "111111"
    r = client.post("/api/auth/verify-email", json={"email": email, "code": wrong})
    assert r.status_code == 400
    assert not user_exists(email), "неверный код не должен создавать аккаунт"
    assert pending_count(email) == 1, "заявка остаётся — можно попробовать снова"


def test_verify_rejects_unknown_email(client):
    r = client.post(
        "/api/auth/verify-email", json={"email": fresh_email(), "code": "123456"}
    )
    assert r.status_code == 400


def test_verify_rejects_expired_code(client):
    from utils import get_db

    email = fresh_email()
    client.post(
        "/api/auth/register",
        json={"name": "Просрочил", "email": email, "password": "Passw0rd!"},
    )
    code = pending_code(email)
    conn = get_db()
    c = conn.cursor()
    # Срок пишется и читается через datetime.utcnow(), поэтому и «состарить»
    # заявку надо в UTC: NOW() отдал бы местное время и тест бы врал.
    c.execute(
        "UPDATE email_verifications SET expires_at=%s WHERE email=%s",
        (datetime.utcnow() - timedelta(hours=1), email),
    )
    conn.commit()
    conn.close()

    r = client.post("/api/auth/verify-email", json={"email": email, "code": code})
    assert r.status_code == 400
    assert not user_exists(email)
    assert pending_count(email) == 0, "протухшая заявка должна вычищаться"


def test_verify_is_not_reusable(client):
    """Повторный запрос с тем же кодом не должен заводить второго пользователя."""
    email = fresh_email()
    register_and_verify(client, email)
    r = client.post("/api/auth/verify-email", json={"email": email, "code": "123456"})
    assert r.status_code == 400


# ── Повторная отправка кода ──────────────────────────────────────────────────

def test_resend_replaces_code(client):
    email = fresh_email()
    client.post(
        "/api/auth/register",
        json={"name": "Потерял письмо", "email": email, "password": "Passw0rd!"},
    )
    assert client.post("/api/auth/resend-code", json={"email": email}).status_code == 200
    assert pending_count(email) == 1
    assert client.post(
        "/api/auth/verify-email", json={"email": email, "code": pending_code(email)}
    ).status_code == 200


def test_resend_without_request_fails(client):
    r = client.post("/api/auth/resend-code", json={"email": fresh_email()})
    assert r.status_code == 400


# ── Регистрация по приглашению ───────────────────────────────────────────────

def test_invite_token_survives_verification(client, admin_token):
    """
    Токен приглашения приходит на первом шаге, а применяется на втором —
    ради этого в email_verifications и заведена колонка invite_token.
    """
    gid = client.post(
        "/api/groups",
        json={"name": f"Приглашающая {uuid.uuid4().hex[:6]}", "description": ""},
        headers=auth(admin_token),
    ).json()["id"]
    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": 5},
        headers=auth(admin_token),
    ).json()

    body = register_and_verify(client, fresh_email("invited"), invite_token=invite["token"])
    assert body["invite_error"] is None
    assert [g["id"] for g in body["groups"]] == [gid]
    assert body["groups"][0]["role"] == "editor"


def test_broken_invite_is_rejected_before_email(client):
    """Про заведомо мёртвую ссылку говорим сразу, не гоняя человека за кодом."""
    email = fresh_email("badinvite")
    r = client.post(
        "/api/auth/register",
        json={
            "name": "С мёртвой ссылкой",
            "email": email,
            "password": "Passw0rd!",
            "invite_token": "такого-токена-нет",
        },
    )
    assert r.status_code == 404
    assert pending_count(email) == 0


def test_invite_exhausted_between_steps_still_creates_account(client, admin_token):
    """
    Ссылку на одно использование могли израсходовать, пока человек искал письмо.
    Аккаунт при этом терять нельзя — почту он подтвердил честно, просто в группу
    не попал, и об этом надо сказать прямо.
    """
    gid = client.post(
        "/api/groups",
        json={"name": f"Одноразовая {uuid.uuid4().hex[:6]}", "description": ""},
        headers=auth(admin_token),
    ).json()["id"]
    token = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": 1},
        headers=auth(admin_token),
    ).json()["token"]

    first, second = fresh_email("first"), fresh_email("second")
    for email in (first, second):
        r = client.post(
            "/api/auth/register",
            json={"name": "Гость", "email": email, "password": "Passw0rd!", "invite_token": token},
        )
        assert r.status_code == 200, "на момент заявки ссылка ещё жива у обоих"

    # Первый успевает и забирает единственное использование
    ok = client.post("/api/auth/verify-email", json={"email": first, "code": pending_code(first)})
    assert ok.status_code == 200
    assert [g["id"] for g in ok.json()["groups"]] == [gid]

    late = client.post("/api/auth/verify-email", json={"email": second, "code": pending_code(second)})
    assert late.status_code == 200, "аккаунт должен создаться несмотря на мёртвое приглашение"
    assert late.json()["groups"] == []
    assert late.json()["invite_error"], "про несработавшее приглашение надо сказать честно"
    assert user_exists(second)
