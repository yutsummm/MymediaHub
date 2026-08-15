"""Ручки вне контекста группы доступны только глобальному администратору."""
import pytest
from conftest import auth

ADMIN_ONLY = [
    ("get", "/api/users"),
    ("get", "/api/settings/vk"),
    ("delete", "/api/settings/vk"),
    ("get", "/api/settings/telegram"),
    ("delete", "/api/settings/telegram"),
    ("post", "/api/posts/sync-vk-stats"),
]


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_regular_user_gets_403(client, make_user, method, path):
    token, _ = make_user("plain")
    assert getattr(client, method)(path, headers=auth(token)).status_code == 403


def test_admin_can_list_users(client, admin_token):
    r = client.get("/api/users", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["total"] >= 3


def test_user_list_never_leaks_password_hash(client, admin_token):
    users = client.get("/api/users", headers=auth(admin_token)).json()["users"]
    assert users
    assert all("password_hash" not in u for u in users)


def test_admin_cannot_delete_self(client, admin_token):
    me = client.post(
        "/api/auth/login", json={"email": "admin@mediahub.ru", "password": "admin123!"}
    ).json()["user"]["id"]
    assert client.delete(f"/api/users/{me}", headers=auth(admin_token)).status_code == 400


def test_admin_cannot_demote_self(client, admin_token):
    me = client.post(
        "/api/auth/login", json={"email": "admin@mediahub.ru", "password": "admin123!"}
    ).json()["user"]["id"]
    r = client.put(f"/api/users/{me}/role", json={"role": "editor"}, headers=auth(admin_token))
    assert r.status_code == 400


def test_role_value_is_validated(client, admin_token, make_user):
    _, victim = make_user("victim")
    r = client.put(
        f"/api/users/{victim}/role", json={"role": "superuser"}, headers=auth(admin_token)
    )
    assert r.status_code == 400


def test_regular_user_cannot_create_user(client, make_user):
    token, _ = make_user("plain")
    r = client.post(
        "/api/users",
        json={"name": "Чужой", "email": "x@y.ru", "role": "admin", "password": "Passw0rd!"},
        headers=auth(token),
    )
    assert r.status_code == 403


def test_regular_user_cannot_delete_other_user(client, make_user):
    token, _ = make_user("plain")
    _, victim = make_user("victim")
    assert client.delete(f"/api/users/{victim}", headers=auth(token)).status_code == 403


def test_volunteer_cannot_create_group_post(client, admin_token, make_user):
    """Волонтёру в группе запись запрещена."""
    token, uid = make_user("volunteer")
    owner = client.post(
        "/api/groups", json={"name": "Группа с волонтёром", "description": ""},
        headers=auth(admin_token),
    ).json()
    gid = owner["id"]

    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "volunteer", "expires_hours": 24, "max_uses": None},
        headers=auth(admin_token),
    )
    assert invite.status_code == 200
    accepted = client.post(f"/api/invites/{invite.json()['token']}/accept", headers=auth(token))
    assert accepted.status_code == 200

    r = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "от волонтёра", "content": "x"},
        headers=auth(token),
    )
    assert r.status_code == 403


def test_non_admin_member_cannot_create_invite(client, admin_token, make_user):
    token, _ = make_user("editor")
    gid = client.post(
        "/api/groups", json={"name": "Группа для инвайта", "description": ""},
        headers=auth(admin_token),
    ).json()["id"]

    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": None},
        headers=auth(admin_token),
    ).json()
    client.post(f"/api/invites/{invite['token']}/accept", headers=auth(token))

    r = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "admin", "expires_hours": 24, "max_uses": None},
        headers=auth(token),
    )
    assert r.status_code == 403
