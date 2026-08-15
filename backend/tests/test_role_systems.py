"""
Две системы ролей должны не пересекаться.

Раньше `users.role` (глобальная) и `group_members.role` (внутри группы)
пользовались одними словами — admin, editor, volunteer — но означали разное:
глобальный «editor» не давал вообще ничего, а групповой давал право публикации.
На бэкенде глобальная роль вообще проверялась ровно на одно значение — 'admin'.

Теперь глобальная роль — только admin/member, групповая — прежняя тройка.
"""
import pytest
from conftest import auth

from utils import GLOBAL_ROLES, GROUP_ROLES, get_db


def global_role(uid: int) -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=%s", (uid,))
    role = c.fetchone()["role"]
    conn.close()
    return role


def group_role(gid: int, uid: int) -> str | None:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM group_members WHERE group_id=%s AND user_id=%s", (gid, uid))
    row = c.fetchone()
    conn.close()
    return row["role"] if row else None


# ── Наборы значений ──────────────────────────────────────────────────────────

def test_role_sets_overlap_only_on_admin():
    """
    Единственное общее слово — «admin», и то в разных таблицах. Всё остальное
    должно различаться, иначе путаница вернётся.
    """
    assert set(GLOBAL_ROLES) & set(GROUP_ROLES) == {"admin"}
    assert "editor" not in GLOBAL_ROLES
    assert "volunteer" not in GLOBAL_ROLES
    assert "member" not in GROUP_ROLES


def test_registration_gives_plain_global_role(client, make_user):
    _, uid = make_user("plain")
    assert global_role(uid) == "member"


def test_database_refuses_foreign_global_role(client, make_user):
    """Схема не должна пускать в users.role групповые значения."""
    import psycopg2

    _, uid = make_user("foreign")
    conn = get_db()
    c = conn.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        c.execute("UPDATE users SET role='volunteer' WHERE id=%s", (uid,))
    conn.rollback()
    conn.close()


# ── Глобальная роль ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["editor", "volunteer", "король", ""])
def test_api_rejects_group_role_as_global(client, admin_token, make_user, bad):
    """Групповое значение нельзя выдать как глобальную роль через API."""
    _, uid = make_user("mix")
    r = client.put(f"/api/users/{uid}/role", json={"role": bad}, headers=auth(admin_token))
    assert r.status_code == 400
    assert global_role(uid) == "member"


def test_global_member_still_works_inside_group(client, group_with_post):
    """
    Обычная глобальная роль ничего не отнимает: права на контент дают группы.
    Раньше это было неочевидно как раз из-за совпадения названий.
    """
    token, uid = group_with_post["token"], group_with_post["user_id"]
    gid = group_with_post["group_id"]
    assert global_role(uid) == "member"
    assert group_role(gid, uid) == "admin"

    r = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "От участника", "content": "т", "platforms": []},
        headers=auth(token),
    )
    assert r.status_code == 200, "групповой админ публикует независимо от глобальной роли"


def test_global_admin_gets_no_extra_group_rights(client, admin_token, make_user):
    """
    И наоборот: глобальный админ не становится автоматически участником чужой
    группы. Системное администрирование и работа с контентом — разные вещи.
    """
    token, _ = make_user("owner-of-group")
    gid = client.post(
        "/api/groups", json={"name": "Чужая", "description": ""}, headers=auth(token)
    ).json()["id"]

    assert client.get(f"/api/groups/{gid}/posts", headers=auth(admin_token)).status_code == 403
    assert client.post(
        f"/api/groups/{gid}/posts", json={"title": "х", "content": "у"}, headers=auth(admin_token)
    ).status_code == 403


# ── Групповая роль ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["member", "король", ""])
def test_group_role_rejects_global_values(client, group_with_post, make_user, bad):
    """
    Раньше сюда не смотрели вовсе: в group_members.role можно было записать что
    угодно, включая глобальное «member», от которого не работает ни одна
    проверка прав — человек оставался в группе без прав и без объяснений.
    """
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    guest_token, guest_id = make_user("guest")
    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": 1},
        headers=auth(token),
    ).json()
    client.post(f"/api/invites/{invite['token']}/accept", headers=auth(guest_token))

    r = client.put(
        f"/api/groups/{gid}/members/{guest_id}/role", json={"role": bad}, headers=auth(token)
    )
    assert r.status_code == 400
    assert group_role(gid, guest_id) == "editor", "роль не должна была измениться"


def test_invite_rejects_global_role(client, group_with_post):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    r = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "member", "expires_hours": 24, "max_uses": 1},
        headers=auth(token),
    )
    assert r.status_code == 400


@pytest.mark.parametrize("good", ["admin", "editor", "volunteer"])
def test_valid_group_roles_are_accepted(client, group_with_post, make_user, good):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    guest_token, guest_id = make_user(f"ok-{good}")
    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": 1},
        headers=auth(token),
    ).json()
    client.post(f"/api/invites/{invite['token']}/accept", headers=auth(guest_token))

    r = client.put(
        f"/api/groups/{gid}/members/{guest_id}/role", json={"role": good}, headers=auth(token)
    )
    assert r.status_code == 200
    assert group_role(gid, guest_id) == good


def test_last_group_admin_cannot_demote_himself(client, group_with_post):
    """
    Симметрично защите глобального админа: иначе группа остаётся без хозяина и
    роли в ней больше некому раздавать.
    """
    token, uid = group_with_post["token"], group_with_post["user_id"]
    gid = group_with_post["group_id"]
    r = client.put(
        f"/api/groups/{gid}/members/{uid}/role", json={"role": "editor"}, headers=auth(token)
    )
    assert r.status_code == 400
    assert group_role(gid, uid) == "admin"
