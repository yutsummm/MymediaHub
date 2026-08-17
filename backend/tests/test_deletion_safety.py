"""
Удаление: смета, подтверждение и след.

Удаление группы уносило участников, приглашения и медиа волонтёров, не
оставляя ничего — ни записи, ни возможности спросить, кто это сделал.
Интерфейс спрашивал «Удалить группу?», а исчезал год работы.

Хуже того, работало оно наполовину. Половина внешних ключей стояла с CASCADE,
половина — без правила вовсе, поэтому поведение зависело от содержимого:
пустую группу удаляло вместе с участниками, а группу хотя бы с одним постом не
удаляло вообще — запрос падал с ForeignKeyViolation и отдавал пятисотку. То же
с пользователем: удалить того, кто написал хоть один пост, было нельзя.

Теперь: правила разведены по смыслу (содержимое группы уходит с ней, следы
человека — остаются без автора), удаление требует подтверждения точным
названием, а всё необратимое пишется в `audit_log`.
"""
import uuid

import pytest
from conftest import auth

from utils import get_db


def make_group(client, token, name=None) -> tuple[int, str]:
    name = name or f"Группа {uuid.uuid4().hex[:6]}"
    r = client.post("/api/groups", json={"name": name, "description": ""}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"], name


def audit_rows(action: str | None = None, object_id: int | None = None) -> list[dict]:
    conn = get_db()
    try:
        c = conn.cursor()
        sql = "SELECT * FROM audit_log WHERE TRUE"
        params: list = []
        if action:
            sql += " AND action=%s"
            params.append(action)
        if object_id is not None:
            sql += " AND object_id=%s"
            params.append(object_id)
        c.execute(sql + " ORDER BY id DESC", params)
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


def count(sql: str, params: tuple) -> int:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        return c.fetchone()["n"]
    finally:
        conn.close()


# ── Смета ────────────────────────────────────────────────────────────────────

def test_preview_says_what_will_disappear(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    r = client.get(f"/api/groups/{gid}/deletion-preview", headers=auth(token))
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["posts"] == 1
    assert preview["members"] == 1
    assert preview["confirm_with"] == preview["name"]


def test_preview_is_for_admins_only(client, group_with_post, make_user):
    """Смета показывает, сколько всего в группе, — это тоже сведения о ней."""
    gid = group_with_post["group_id"]
    stranger, _ = make_user("чужой")
    assert client.get(
        f"/api/groups/{gid}/deletion-preview", headers=auth(stranger)
    ).status_code == 403


# ── Подтверждение ────────────────────────────────────────────────────────────

def test_delete_without_confirmation_is_refused(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    r = client.delete(f"/api/groups/{gid}", headers=auth(token))
    assert r.status_code == 409
    # Отказ обязан объяснять, что именно на кону.
    assert "название группы" in r.json()["detail"]
    assert count("SELECT COUNT(*) n FROM groups WHERE id=%s", (gid,)) == 1


def test_wrong_confirmation_is_refused(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    r = client.delete(f"/api/groups/{gid}?confirm=не то название", headers=auth(token))
    assert r.status_code == 409
    assert count("SELECT COUNT(*) n FROM groups WHERE id=%s", (gid,)) == 1


def test_exact_name_deletes_the_group(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    name = client.get(f"/api/groups/{gid}", headers=auth(token)).json()["name"]
    r = client.delete(f"/api/groups/{gid}", params={"confirm": name}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert count("SELECT COUNT(*) n FROM groups WHERE id=%s", (gid,)) == 0


# ── Регрессия: раньше это была пятисотка ─────────────────────────────────────

def test_group_with_content_can_be_deleted_at_all(client, group_with_post):
    """
    Регрессия. posts.group_id ссылался на groups без правила удаления, поэтому
    группу хотя бы с одним постом удалить было физически нельзя: psycopg2
    поднимал ForeignKeyViolation, никто его не ловил, пользователь получал 500.
    """
    gid, token = group_with_post["group_id"], group_with_post["token"]
    name = client.get(f"/api/groups/{gid}", headers=auth(token)).json()["name"]
    r = client.delete(f"/api/groups/{gid}", params={"confirm": name}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert count("SELECT COUNT(*) n FROM posts WHERE group_id=%s", (gid,)) == 0
    assert count("SELECT COUNT(*) n FROM group_members WHERE group_id=%s", (gid,)) == 0
    assert count("SELECT COUNT(*) n FROM invite_links WHERE group_id=%s", (gid,)) == 0


def test_deleting_group_takes_its_integrations(client, group_with_post, db):
    """Интеграции без группы бессмысленны и мешали её удалить."""
    gid, token = group_with_post["group_id"], group_with_post["token"]
    c = db.cursor()
    c.execute(
        "INSERT INTO tg_settings (bot_token, chat_id, chat_title, workspace_id) "
        "VALUES ('токен', '@канал', 'Канал', %s)",
        (gid,),
    )
    db.commit()
    name = client.get(f"/api/groups/{gid}", headers=auth(token)).json()["name"]
    assert client.delete(
        f"/api/groups/{gid}", params={"confirm": name}, headers=auth(token)
    ).status_code == 200
    assert count("SELECT COUNT(*) n FROM tg_settings WHERE workspace_id=%s", (gid,)) == 0


# ── Пользователь: следы остаются ─────────────────────────────────────────────

def test_user_with_posts_can_be_deleted_and_posts_survive(client, admin_token, make_user):
    """
    Работа организации не должна исчезать вместе с уволившимся сотрудником —
    и не должна мешать его удалить. Раньше было ровно наоборот.
    """
    token, uid = make_user("автор")
    gid, _ = make_group(client, token)
    post = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Останется", "content": "текст", "status": "draft"},
        headers=auth(token),
    ).json()

    preview = client.get(f"/api/users/{uid}/deletion-preview", headers=auth(admin_token))
    assert preview.status_code == 200, preview.text
    email = preview.json()["email"]
    assert preview.json()["posts_kept"] == 1

    r = client.delete(f"/api/users/{uid}", params={"confirm": email}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert count("SELECT COUNT(*) n FROM users WHERE id=%s", (uid,)) == 0
    assert count("SELECT COUNT(*) n FROM posts WHERE id=%s", (post["id"],)) == 1
    assert count(
        "SELECT COUNT(*) n FROM posts WHERE id=%s AND author_id IS NULL", (post["id"],)
    ) == 1


def test_user_deletion_needs_exact_email(client, admin_token, make_user):
    _, uid = make_user("подтверждение")
    r = client.delete(f"/api/users/{uid}", headers=auth(admin_token))
    assert r.status_code == 409
    assert "email" in r.json()["detail"]
    assert count("SELECT COUNT(*) n FROM users WHERE id=%s", (uid,)) == 1


def test_preview_warns_about_sole_admin(client, admin_token, make_user):
    """Человек — единственный админ своей группы: после удаления ею некому управлять."""
    token, uid = make_user("единственный")
    _, name = make_group(client, token)
    preview = client.get(f"/api/users/{uid}/deletion-preview", headers=auth(admin_token)).json()
    assert name in preview["sole_admin_of"]


# ── Журнал ───────────────────────────────────────────────────────────────────

def test_group_deletion_leaves_a_record(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    name = client.get(f"/api/groups/{gid}", headers=auth(token)).json()["name"]
    client.delete(f"/api/groups/{gid}", params={"confirm": name}, headers=auth(token))

    rows = audit_rows("group.deleted", gid)
    assert rows, "удаление группы не оставило следа"
    record = rows[0]
    # Название и счётчики — снимок: спросить их после удаления уже не у кого.
    assert record["object_label"] == name
    assert record["details"]["posts"] == 1
    assert record["actor_id"] == group_with_post["user_id"]
    assert record["actor_email"]


def test_record_survives_the_group_it_describes(client, group_with_post):
    """Запись переживает удалённое: иначе журнал пуст ровно там, где нужен."""
    gid, token = group_with_post["group_id"], group_with_post["token"]
    name = client.get(f"/api/groups/{gid}", headers=auth(token)).json()["name"]
    client.delete(f"/api/groups/{gid}", params={"confirm": name}, headers=auth(token))
    assert count("SELECT COUNT(*) n FROM groups WHERE id=%s", (gid,)) == 0
    assert audit_rows("group.deleted", gid), "запись ушла вместе с группой"


def test_post_deletion_is_recorded(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    pid = group_with_post["post"]["id"]
    client.delete(f"/api/groups/{gid}/posts/{pid}", headers=auth(token))
    rows = audit_rows("post.deleted", pid)
    assert rows and rows[0]["object_label"] == group_with_post["post"]["title"]


def test_member_removal_and_role_change_are_recorded(client, group_with_post, make_user):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    guest, guest_id = make_user("гость")
    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": 5},
        headers=auth(token),
    ).json()
    client.post(f"/api/invites/{invite['token']}/accept", headers=auth(guest))

    client.put(
        f"/api/groups/{gid}/members/{guest_id}/role",
        json={"role": "volunteer"}, headers=auth(token),
    )
    changed = audit_rows("group.member_role_changed", guest_id)
    assert changed and changed[0]["details"] == {"было": "editor", "стало": "volunteer"}

    client.delete(f"/api/groups/{gid}/members/{guest_id}", headers=auth(token))
    assert audit_rows("group.member_removed", guest_id)


def test_integration_disconnect_is_recorded(client, group_with_post, db):
    """
    После отключения посты перестают уходить в паблик, а по интерфейсу это
    выглядит как «ничего не происходит». Вопрос «кто отключил» возникает всегда.
    """
    gid, token = group_with_post["group_id"], group_with_post["token"]
    c = db.cursor()
    c.execute(
        "INSERT INTO tg_settings (bot_token, chat_id, chat_title, workspace_id) "
        "VALUES ('токен', '@канал', 'Канал', %s)",
        (gid,),
    )
    db.commit()
    r = client.delete(f"/api/groups/{gid}/settings/telegram", headers=auth(token))
    assert r.status_code == 200, r.text
    rows = [x for x in audit_rows("integration.disconnected") if x["group_id"] == gid]
    assert rows and rows[0]["object_label"] == "Telegram"


# ── Кто может читать журнал ──────────────────────────────────────────────────

def test_group_log_is_for_group_admins(client, group_with_post, make_user):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    assert client.get(f"/api/groups/{gid}/audit", headers=auth(token)).status_code == 200
    stranger, _ = make_user("посторонний")
    assert client.get(f"/api/groups/{gid}/audit", headers=auth(stranger)).status_code == 403


def test_group_log_shows_only_its_own_events(client, group_with_post, make_user):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    other_token, _ = make_user("сосед")
    other_gid, other_name = make_group(client, other_token)
    client.delete(
        f"/api/groups/{other_gid}", params={"confirm": other_name}, headers=auth(other_token)
    )
    items = client.get(f"/api/groups/{gid}/audit", headers=auth(token)).json()["items"]
    assert all(i["group_id"] == gid for i in items), "в журнал группы попали чужие события"


def test_whole_log_is_for_global_admins(client, admin_token, make_user):
    r = client.get("/api/audit", headers=auth(admin_token))
    assert r.status_code == 200
    assert "total" in r.json()
    token, _ = make_user("не-админ")
    assert client.get("/api/audit", headers=auth(token)).status_code == 403


def test_log_can_be_filtered_by_action(client, admin_token):
    r = client.get("/api/audit?action=group.deleted", headers=auth(admin_token))
    assert r.status_code == 200
    assert all(i["action"] == "group.deleted" for i in r.json()["items"])


@pytest.fixture(autouse=True)
def _keep_log_readable():
    """Журнал общий на всю сессию тестов — чистим перед каждым, чтобы не мешались."""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM audit_log")
        conn.commit()
    finally:
        conn.close()
    yield
