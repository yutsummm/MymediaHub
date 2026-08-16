"""
Токен должен быть отзываемым.

JWT проверялся только подписью, без обращения к базе — отозвать его было нельзя
ничем. Выход существовал лишь на клиенте: приложение забывало токен, а сам
токен оставался действительным ещё до 72 часов. Украденный токен работал всё
это время, и смена пароля от этого не спасала.
"""
from datetime import UTC, datetime, timedelta, timezone

import pytest
from conftest import auth, pending_code

from utils import get_db, list_sessions, purge_sessions, revoke_user_sessions


def sessions_of(user_id: int) -> list[dict]:
    return list_sessions(user_id)


def works(client, token: str) -> bool:
    return client.get("/api/groups", headers=auth(token)).status_code == 200


# ── Выход действительно гасит токен ──────────────────────────────────────────

def test_logout_kills_the_token(client, make_user):
    """Главное свойство, которого не было: после выхода токен не работает."""
    token, _ = make_user("logout")
    assert works(client, token)

    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 200
    assert not works(client, token), "токен должен перестать действовать сразу"


def test_logout_does_not_touch_other_devices(client, make_user):
    token_a, uid = make_user("two-devices")
    # второй вход тем же человеком — как вход с другого устройства
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=%s", (uid,))
    email = c.fetchone()["email"]
    conn.close()
    token_b = client.post(
        "/api/auth/login", json={"email": email, "password": "Passw0rd!"}
    ).json()["token"]

    client.post("/api/auth/logout", headers=auth(token_a))
    assert not works(client, token_a)
    assert works(client, token_b), "выход на одном устройстве не должен выкидывать с другого"


def test_logout_everywhere_kills_the_rest(client, make_user):
    token_a, uid = make_user("everywhere")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=%s", (uid,))
    email = c.fetchone()["email"]
    conn.close()
    token_b = client.post(
        "/api/auth/login", json={"email": email, "password": "Passw0rd!"}
    ).json()["token"]

    r = client.post("/api/auth/logout-all", headers=auth(token_a))
    assert r.status_code == 200
    assert r.json()["sessions_revoked"] >= 1
    assert not works(client, token_b), "чужие устройства должны отвалиться"
    assert works(client, token_a), "текущее устройство остаётся — иначе это просто выход"


def test_second_logout_is_harmless(client, make_user):
    token, _ = make_user("double-logout")
    client.post("/api/auth/logout", headers=auth(token))
    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 401


# ── Смена пароля ─────────────────────────────────────────────────────────────

def test_password_reset_revokes_stolen_tokens(client, make_user):
    """
    Ровно тот сценарий, ради которого всё это: токен увели, человек меняет
    пароль — старый токен обязан умереть. Раньше он продолжал работать.
    """
    token, uid = make_user("reset")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=%s", (uid,))
    email = c.fetchone()["email"]
    conn.close()

    assert works(client, token)
    client.post("/api/auth/forgot-password", json={"email": email})
    code = _reset_code(email)
    r = client.post(
        "/api/auth/reset-password",
        json={"email": email, "code": code, "new_password": "NewPassw0rd!"},
    )
    assert r.status_code == 200
    assert r.json()["sessions_revoked"] >= 1
    assert not works(client, token), "после смены пароля старый токен должен умереть"


def _reset_code(email: str) -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT code FROM password_resets WHERE email=%s ORDER BY id DESC LIMIT 1", (email,))
    row = c.fetchone()
    conn.close()
    assert row, "код сброса не найден"
    return row["code"]


def test_registration_code_flow_still_issues_working_token(client):
    """Подтверждение почты тоже должно заводить нормальную сессию."""
    import uuid

    email = f"sess-{uuid.uuid4().hex[:8]}@test.local"
    client.post(
        "/api/auth/register",
        json={"name": "Сессия", "email": email, "password": "Passw0rd!"},
    )
    body = client.post(
        "/api/auth/verify-email", json={"email": email, "code": pending_code(email)}
    ).json()
    assert works(client, body["token"])
    assert len(sessions_of(body["user"]["id"])) == 1


# ── Просмотр входов ──────────────────────────────────────────────────────────

def test_user_sees_his_active_sessions(client, make_user):
    token, uid = make_user("visible")
    r = client.get("/api/auth/sessions", headers=auth(token))
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["current"] is True
    assert "jti" not in sessions[0], "идентификатор сессии равносилен ссылке на неё"
    assert uid


def test_revoked_session_disappears_from_the_list(client, make_user):
    token, uid = make_user("disappear")
    revoke_user_sessions(uid, "проверка")
    assert sessions_of(uid) == []


# ── Отказ в доступе ──────────────────────────────────────────────────────────

def test_token_without_session_is_rejected(client, make_user):
    """
    Токены, выписанные до появления сессий, отозвать нельзя — значит и
    принимать их нельзя.
    """
    from jose import jwt

    from utils import JWT_ALGORITHM, JWT_SECRET

    _, uid = make_user("legacy")
    legacy = jwt.encode(
        {"sub": str(uid), "exp": datetime.utcnow() + timedelta(hours=1)},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )
    assert not works(client, legacy)


def test_token_for_another_user_is_rejected(client, make_user):
    """Подмена sub при живой чужой сессии не должна проходить."""
    from jose import jwt

    from utils import JWT_ALGORITHM, JWT_SECRET

    token, uid = make_user("victim")
    other_token, other_uid = make_user("attacker")
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    forged = jwt.encode(
        {"sub": str(other_uid), "exp": datetime.utcnow() + timedelta(hours=1),
         "jti": payload["jti"]},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )
    assert not works(client, forged)
    assert works(client, other_token)


def test_expired_session_is_rejected_even_with_valid_signature(client, make_user):
    """База — источник правды по сроку: подпись может быть ещё жива."""
    from jose import jwt

    from utils import JWT_ALGORITHM, JWT_SECRET

    token, _ = make_user("expired")
    jti = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])["jti"]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE sessions SET expires_at = NOW() - INTERVAL '1 hour' WHERE jti=%s", (jti,))
    conn.commit()
    conn.close()
    assert not works(client, token)


@pytest.mark.parametrize("header", [None, "Bearer", "Bearer not-a-jwt", "Basic abc"])
def test_broken_authorization_is_rejected(client, header):
    headers = {"Authorization": header} if header else {}
    assert client.get("/api/groups", headers=headers).status_code == 401


# ── Обслуживание ─────────────────────────────────────────────────────────────

def test_last_seen_is_recorded(client, make_user):
    token, uid = make_user("seen")
    works(client, token)
    session = sessions_of(uid)[0]
    assert session["last_seen_at"] is not None
    assert (datetime.now(UTC) - session["last_seen_at"]).total_seconds() < 120


def test_purge_removes_only_long_expired(client, make_user):
    token, uid = make_user("purge")
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (jti, user_id, expires_at) VALUES ('древняя', %s, NOW() - INTERVAL '30 days')",
        (uid,),
    )
    conn.commit()
    conn.close()

    assert purge_sessions() >= 1
    assert works(client, token), "живая сессия не должна пострадать"

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM sessions WHERE jti='древняя'")
    gone = c.fetchone() is None
    conn.close()
    assert gone
