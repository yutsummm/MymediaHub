"""
Регистрация не должна давать доступ к чужой группе.

До исправления новый пользователь молча попадал в первую группу
(ORDER BY id ASC LIMIT 1) с ролью editor — то есть любой посторонний после
регистрации мог опубликовать пост в реальные VK-паблик и Telegram-канал
организации. Эти тесты стерегут именно этот сценарий.
"""
import uuid

import pytest
from conftest import auth, pending_code


def _register(client, prefix="stranger", invite_token=None):
    """
    Полный путь регистрации: заявка → код из базы → аккаунт. Отдаёт ответ того
    шага, на котором всё закончилось, поэтому проверки статусов ниже работают
    и для отказов на первом шаге (битая или исчерпанная ссылка).
    """
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.local"
    body = {"name": "Посторонний", "email": email, "password": "Passw0rd!"}
    if invite_token is not None:
        body["invite_token"] = invite_token
    r = client.post("/api/auth/register", json=body)
    if r.status_code != 200:
        return r
    return client.post(
        "/api/auth/verify-email", json={"email": email, "code": pending_code(email)}
    )


# ── Главное: чужих групп новичок не получает ────────────────────────────────

def test_new_user_joins_no_group(client, group_with_post):
    """Регистрация не втягивает ни в одну существующую группу."""
    r = _register(client)
    assert r.status_code == 200
    assert r.json()["groups"] == []


def test_new_user_sees_no_groups_via_api(client, group_with_post):
    r = _register(client)
    token = r.json()["token"]
    assert client.get("/api/groups", headers=auth(token)).json() == []


def test_new_user_cannot_read_existing_group(client, group_with_post):
    token = _register(client).json()["token"]
    gid = group_with_post["group_id"]
    assert client.get(f"/api/groups/{gid}", headers=auth(token)).status_code == 403
    assert client.get(f"/api/groups/{gid}/posts", headers=auth(token)).status_code == 403


def test_new_user_cannot_publish_to_existing_group(client, group_with_post):
    """Ключевой сценарий: посторонний не может отправить пост в паблик организации."""
    token = _register(client).json()["token"]
    gid = group_with_post["group_id"]

    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "От постороннего", "content": "текст"},
        headers=auth(token),
    )
    assert created.status_code == 403

    pid = group_with_post["post"]["id"]
    assert client.post(f"/api/groups/{gid}/posts/{pid}/publish", headers=auth(token)).status_code == 403
    assert client.post(f"/api/posts/{pid}/publish", headers=auth(token)).status_code == 403


def test_new_user_sees_no_foreign_posts(client, group_with_post):
    token = _register(client).json()["token"]
    body = client.get("/api/posts", headers=auth(token)).json()
    assert body["posts"] == []
    assert body["total"] == 0


def test_new_user_analytics_is_empty(client, group_with_post):
    token = _register(client).json()["token"]
    assert client.get("/api/analytics/summary", headers=auth(token)).json()["total_posts"] == 0


# ── Регистрация по приглашению ──────────────────────────────────────────────

@pytest.fixture()
def invite_link(client, admin_token):
    """Действующее приглашение в свежую группу с ролью volunteer."""
    gid = client.post(
        "/api/groups",
        json={"name": f"Группа {uuid.uuid4().hex[:6]}", "description": ""},
        headers=auth(admin_token),
    ).json()["id"]
    link = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "volunteer", "expires_hours": 24, "max_uses": 1},
        headers=auth(admin_token),
    )
    assert link.status_code == 200, link.text
    return {"group_id": gid, **link.json()}


def test_register_with_invite_joins_that_group(client, invite_link):
    r = _register(client, "invited", invite_token=invite_link["token"])
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert [g["id"] for g in groups] == [invite_link["group_id"]]


def test_register_with_invite_uses_role_from_link(client, invite_link):
    """Роль берётся из приглашения, а не выдаётся по умолчанию editor."""
    r = _register(client, "invited", invite_token=invite_link["token"])
    assert r.json()["groups"][0]["role"] == "volunteer"


def test_invited_volunteer_still_cannot_publish(client, invite_link):
    """Приглашение с ролью volunteer не даёт права публикации."""
    token = _register(client, "invited", invite_token=invite_link["token"]).json()["token"]
    gid = invite_link["group_id"]
    r = client.post(
        f"/api/groups/{gid}/posts", json={"title": "х", "content": "у"}, headers=auth(token)
    )
    assert r.status_code == 403


def test_register_with_unknown_invite_creates_nothing(client):
    """Битый токен отбивается сразу, до письма, и не создаёт «висячего» пользователя."""
    email = f"ghost-{uuid.uuid4().hex[:8]}@test.local"
    r = client.post(
        "/api/auth/register",
        json={"name": "Призрак", "email": email, "password": "Passw0rd!", "invite_token": "нет-такого"},
    )
    assert r.status_code == 404
    # раз регистрация не удалась, тем же адресом можно зарегистрироваться заново
    again = client.post(
        "/api/auth/register", json={"name": "Призрак", "email": email, "password": "Passw0rd!"}
    )
    assert again.status_code == 200


def test_invite_max_uses_is_enforced(client, invite_link):
    """Ссылка на одно использование не должна срабатывать дважды."""
    first = _register(client, "first", invite_token=invite_link["token"])
    assert first.status_code == 200
    second = _register(client, "second", invite_token=invite_link["token"])
    assert second.status_code == 410


def test_expired_invite_rejected(client, admin_token):
    gid = client.post(
        "/api/groups", json={"name": "Просроченная", "description": ""}, headers=auth(admin_token)
    ).json()["id"]
    link = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": -1, "max_uses": None},
        headers=auth(admin_token),
    ).json()
    assert _register(client, "late", invite_token=link["token"]).status_code == 410
