"""
Администратора должно быть возможно назначить.

Глобальную роль меняет только другой администратор, а регистрация всем выдаёт
editor. Стоит остаться без рабочего админа — и назначить нового физически
некем: управление пользователями закрывается навсегда. Плюс сама страница
управления в интерфейсе просто отсутствовала, хотя ручки были готовы.
"""
import os

import pytest
from conftest import auth

import main
from utils import get_db


def role_of(email: str) -> str | None:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE email=%s", (email.lower(),))
    row = c.fetchone()
    conn.close()
    return row["role"] if row else None


# ── Назначение через API ─────────────────────────────────────────────────────

def test_admin_can_promote_another_user(client, admin_token, make_user):
    """Ровно то, ради чего заводилась страница: сделать нового администратора."""
    token, uid = make_user("promote")
    assert client.get("/api/users", headers=auth(token)).status_code == 403

    r = client.put(f"/api/users/{uid}/role", json={"role": "admin"}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    # и новый админ сразу может работать с пользователями
    assert client.get("/api/users", headers=auth(token)).status_code == 200


def test_non_admin_cannot_promote_anyone(client, make_user):
    _, victim = make_user("victim")
    token, _ = make_user("nobody")
    r = client.put(f"/api/users/{victim}/role", json={"role": "admin"}, headers=auth(token))
    assert r.status_code == 403


def test_admin_cannot_demote_himself(client, admin_token, make_user):
    """Иначе последний админ снимает себя и запирает всех снаружи."""
    me = client.get("/api/users", headers=auth(admin_token)).json()["users"]
    admin_id = next(u["id"] for u in me if u["email"] == "admin@mediahub.ru")
    r = client.put(f"/api/users/{admin_id}/role", json={"role": "editor"}, headers=auth(admin_token))
    assert r.status_code == 400


def test_unknown_role_is_rejected(client, admin_token, make_user):
    _, uid = make_user("badrole")
    r = client.put(f"/api/users/{uid}/role", json={"role": "король"}, headers=auth(admin_token))
    assert r.status_code == 400


def test_admin_can_create_user_with_role(client, admin_token):
    r = client.post(
        "/api/users",
        json={"name": "Новый Админ", "email": "created-admin@test.local",
              "role": "admin", "password": "Passw0rd!"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    login = client.post(
        "/api/auth/login", json={"email": "created-admin@test.local", "password": "Passw0rd!"}
    )
    assert login.status_code == 200, "созданный админ должен уметь входить"


def test_created_user_password_is_validated(client, admin_token):
    r = client.post(
        "/api/users",
        json={"name": "Слабый", "email": "weak-admin@test.local", "role": "admin", "password": "123"},
        headers=auth(admin_token),
    )
    assert r.status_code == 400


# ── Страховка от запирания ───────────────────────────────────────────────────

def test_admin_presence_is_detected(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    assert main.ensure_admin_exists() is True


def test_missing_usable_admin_is_reported(monkeypatch, caplog):
    """
    Админ с пустым паролем (посевной admin@mediahub.ru) роль занимает, а войти
    им нельзя — это и есть запертая система, и её надо замечать.
    """
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE role='admin'")
    saved = [(r["id"], r["password_hash"]) for r in c.fetchall()]
    c.execute("UPDATE users SET password_hash=NULL WHERE role='admin'")
    conn.commit()
    try:
        assert main.ensure_admin_exists() is False
        assert "нет ни одного администратора" in caplog.text
    finally:
        for uid, ph in saved:
            c.execute("UPDATE users SET password_hash=%s WHERE id=%s", (ph, uid))
        conn.commit()
        conn.close()


def test_bootstrap_env_promotes_existing_user(client, make_user, monkeypatch, caplog):
    """Выход из запертого состояния: почта в переменной — и человек стал админом."""
    token, uid = make_user("bootstrap")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=%s", (uid,))
    email = c.fetchone()["email"]
    conn.close()

    assert role_of(email) == "member", "регистрация даёт обычную глобальную роль"
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", email.upper())  # регистр не должен мешать
    main.ensure_admin_exists()
    assert role_of(email) == "admin"
    assert "назначен администратором" in caplog.text
    assert client.get("/api/users", headers=auth(token)).status_code == 200


def test_bootstrap_is_idempotent(client, make_user, monkeypatch, caplog):
    """Переменную забудут убрать — повторный старт не должен ничего ломать."""
    _, uid = make_user("twice")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=%s", (uid,))
    email = c.fetchone()["email"]
    conn.close()

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", email)
    main.ensure_admin_exists()
    caplog.clear()
    main.ensure_admin_exists()
    assert "назначен администратором" not in caplog.text
    assert role_of(email) == "admin"


def test_bootstrap_with_unknown_email_warns(monkeypatch, caplog):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "нет-такого@test.local")
    main.ensure_admin_exists()
    assert "такого пользователя нет" in caplog.text


@pytest.fixture(autouse=True)
def _clean_bootstrap_env():
    saved = os.environ.pop("BOOTSTRAP_ADMIN_EMAIL", None)
    yield
    if saved is not None:
        os.environ["BOOTSTRAP_ADMIN_EMAIL"] = saved
