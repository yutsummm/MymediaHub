"""
Сброс пароля целиком: запрос кода → смена пароля → вход с новым паролем.
Отправку письма подменяем — SMTP в тестах не нужен.
"""
import uuid

import pytest
from conftest import auth

import routers.auth as auth_module


@pytest.fixture()
def captured_codes(monkeypatch):
    """Перехватывает код подтверждения вместо отправки письма."""
    sent = {}

    def fake_send(to_email: str, code: str):
        sent[to_email] = code

    monkeypatch.setattr(auth_module, "send_reset_email", fake_send)
    return sent


@pytest.fixture()
def registered_user(client):
    email = f"reset-{uuid.uuid4().hex[:8]}@test.local"
    r = client.post(
        "/api/auth/register",
        json={"name": "Сброс Тест", "email": email, "password": "OldPassw0rd!"},
    )
    assert r.status_code == 200, r.text
    return email


def test_forgot_password_issues_code(client, registered_user, captured_codes):
    r = client.post("/api/auth/forgot-password", json={"email": registered_user})
    assert r.status_code == 200
    assert registered_user in captured_codes
    assert captured_codes[registered_user].isdigit()


def test_full_reset_flow(client, registered_user, captured_codes):
    client.post("/api/auth/forgot-password", json={"email": registered_user})
    code = captured_codes[registered_user]

    r = client.post(
        "/api/auth/reset-password",
        json={"email": registered_user, "code": code, "new_password": "NewPassw0rd!"},
    )
    assert r.status_code == 200

    old = client.post(
        "/api/auth/login", json={"email": registered_user, "password": "OldPassw0rd!"}
    )
    assert old.status_code == 401

    new = client.post(
        "/api/auth/login", json={"email": registered_user, "password": "NewPassw0rd!"}
    )
    assert new.status_code == 200
    assert client.get("/api/groups", headers=auth(new.json()["token"])).status_code == 200


def test_reset_rejects_wrong_code(client, registered_user, captured_codes):
    client.post("/api/auth/forgot-password", json={"email": registered_user})
    r = client.post(
        "/api/auth/reset-password",
        json={"email": registered_user, "code": "000000", "new_password": "NewPassw0rd!"},
    )
    assert r.status_code == 400


def test_reset_without_request_returns_400(client, registered_user):
    r = client.post(
        "/api/auth/reset-password",
        json={"email": registered_user, "code": "123456", "new_password": "NewPassw0rd!"},
    )
    assert r.status_code == 400


def test_reset_validates_new_password(client, registered_user, captured_codes):
    client.post("/api/auth/forgot-password", json={"email": registered_user})
    code = captured_codes[registered_user]
    r = client.post(
        "/api/auth/reset-password",
        json={"email": registered_user, "code": code, "new_password": "слабый"},
    )
    assert r.status_code == 400


def test_forgot_password_hides_unknown_email(client, captured_codes):
    """Ответ одинаковый и для существующего, и для несуществующего адреса."""
    r = client.post("/api/auth/forgot-password", json={"email": "нет-такого@test.local"})
    assert r.status_code == 200
    assert r.json()["status"] == "code_sent"
    assert "нет-такого@test.local" not in captured_codes


def test_forgot_password_is_rate_limited(client, registered_user, captured_codes):
    """4-й запрос подряд с одного адреса должен упереться в лимит."""
    for _ in range(3):
        assert client.post(
            "/api/auth/forgot-password", json={"email": registered_user}
        ).status_code == 200
    r = client.post("/api/auth/forgot-password", json={"email": registered_user})
    assert r.status_code == 429
