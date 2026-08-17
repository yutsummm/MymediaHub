"""
Согласование постов: редактор готовит — администратор группы выпускает.

Стережём три вещи, каждая из которых уже была бы дырой:

1. **Закрыты все выходы, а не кнопка «Опубликовать».** Пост уходит людям тремя
   разными путями: статус `published` при создании, статус `scheduled` (его
   подхватит планировщик) и ручка публикации. Закрыть один из них и оставить
   два — то же самое, что не закрывать ничего.
2. **Одобренный пост уходит туда, куда собирался.** Есть будущая
   `scheduled_at` — в расписание, нет — сразу в публикацию.
3. **Существующие группы не встают.** Молча включить согласование везде нельзя:
   там, где единственный активный человек — редактор, публиковать стало бы
   некому, и группа замерла бы без единого сообщения об ошибке.
"""
import uuid

import pytest
from conftest import auth
from test_migration_on_legacy_db import _alembic, legacy_db  # noqa: F401 — фикстура

from utils import get_db


def make_group(client, token: str, approval: bool) -> int:
    r = client.post(
        "/api/groups",
        json={"name": f"Группа {uuid.uuid4().hex[:6]}", "description": ""},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    # Новые группы приходят с согласованием — выключаем, когда тест хочет иначе.
    r = client.put(f"/api/groups/{gid}", json={"require_approval": approval},
                   headers=auth(token))
    assert r.status_code == 200, r.text
    return gid


def add_member(client, admin_token: str, gid: int, member_token: str, role: str) -> None:
    link = client.post(f"/api/groups/{gid}/invites", json={"role": role, "expires_hours": 24},
                       headers=auth(admin_token))
    assert link.status_code == 200, link.text
    r = client.post(f"/api/invites/{link.json()['token']}/accept", headers=auth(member_token))
    assert r.status_code == 200, r.text


def make_post(client, token: str, gid: int, **fields) -> dict:
    payload = {"title": f"Пост {uuid.uuid4().hex[:6]}", "content": "текст", "status": "draft"}
    payload.update(fields)
    r = client.post(f"/api/groups/{gid}/posts", json=payload, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def post_status(post_id: int) -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    conn.close()
    return row["status"]


@pytest.fixture()
def crew(client, make_user):
    """Группа с обязательным согласованием: администратор и редактор."""
    admin, admin_id = make_user("approver")
    editor, editor_id = make_user("writer")
    gid = make_group(client, admin, approval=True)
    add_member(client, admin, gid, editor, "editor")
    return {"gid": gid, "admin": admin, "admin_id": admin_id,
            "editor": editor, "editor_id": editor_id}


# ── Новая группа получает согласование, старые — нет ─────────────────────────

def test_new_group_requires_approval_by_default(client, make_user):
    token, _ = make_user("fresh")
    r = client.post("/api/groups", json={"name": f"Новая {uuid.uuid4().hex[:6]}"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["require_approval"] is True


def test_migration_leaves_existing_groups_alone(legacy_db):  # noqa: F811 — фикстура из соседнего модуля
    """
    Группы, заведённые до появления согласования, обязаны работать как прежде.

    Проверять это на уже мигрированной базе нельзя: любая группа, созданная
    после миграции, получает согласование по умолчанию — то есть тест на
    посеянной группе доказывал бы ровно обратное тому, что нужно. Поэтому катим
    цепочку до предыдущей ревизии, заводим группу «из прошлого» и смотрим, что
    с ней сделает миграция.

    Цена — отдельная база на тест. Она дешевле, чем выкатка, которая молча
    остановит публикации у всех, кто уже пользуется системой.
    """
    import psycopg2

    command, cfg = _alembic(legacy_db)
    command.upgrade(cfg, "b2e6a3d95f41")

    conn = psycopg2.connect(legacy_db)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO groups (name, description) VALUES ('Из прошлого', '') RETURNING id"
    )
    old_gid = cur.fetchone()[0]
    conn.close()

    command.upgrade(cfg, "head")

    conn = psycopg2.connect(legacy_db)
    cur = conn.cursor()
    cur.execute("SELECT require_approval FROM groups WHERE id=%s", (old_gid,))
    assert cur.fetchone()[0] is False, "существующей группе включили согласование"

    # А заведённая после миграции — уже с согласованием.
    cur.execute("INSERT INTO groups (name, description) VALUES ('Новая', '') RETURNING id")
    new_gid = cur.fetchone()[0]
    cur.execute("SELECT require_approval FROM groups WHERE id=%s", (new_gid,))
    assert cur.fetchone()[0] is True, "новая группа должна требовать согласования"
    conn.close()


# ── Все три выхода закрыты ──────────────────────────────────────────────────

def test_editor_cannot_create_published_post(client, crew):
    r = client.post(
        f"/api/groups/{crew['gid']}/posts",
        json={"title": "Мимо визы", "content": "текст", "status": "published"},
        headers=auth(crew["editor"]),
    )
    assert r.status_code == 403
    assert "согласован" in r.json()["detail"].lower()


def test_editor_cannot_schedule_post(client, crew):
    """
    Отложенный пост опаснее прямой публикации: он выйдет сам, без второго
    нажатия, и заметят это уже в ленте.
    """
    r = client.post(
        f"/api/groups/{crew['gid']}/posts",
        json={"title": "Мимо визы отложенно", "content": "текст",
              "status": "scheduled", "scheduled_at": "2027-01-01T10:00"},
        headers=auth(crew["editor"]),
    )
    assert r.status_code == 403


def test_editor_cannot_switch_draft_to_scheduled(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    r = client.put(
        f"/api/groups/{crew['gid']}/posts/{post['id']}",
        json={"status": "scheduled", "scheduled_at": "2027-01-01T10:00"},
        headers=auth(crew["editor"]),
    )
    assert r.status_code == 403
    assert post_status(post["id"]) == "draft"


def test_editor_cannot_call_publish_endpoint(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/publish",
                    headers=auth(crew["editor"]))
    assert r.status_code == 403


def test_admin_publishes_without_review(client, crew):
    """Администратор группы и есть тот, кто визирует, — визы у себя не просит."""
    r = client.post(
        f"/api/groups/{crew['gid']}/posts",
        json={"title": "Своей властью", "content": "текст",
              "status": "scheduled", "scheduled_at": "2027-01-01T10:00"},
        headers=auth(crew["admin"]),
    )
    assert r.status_code == 200, r.text


def test_group_without_approval_publishes_as_before(client, make_user):
    admin, _ = make_user("free-admin")
    editor, _ = make_user("free-editor")
    gid = make_group(client, admin, approval=False)
    add_member(client, admin, gid, editor, "editor")
    r = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Как раньше", "content": "текст",
              "status": "scheduled", "scheduled_at": "2027-01-01T10:00"},
        headers=auth(editor),
    )
    assert r.status_code == 200, r.text


# ── Маршрут согласования ────────────────────────────────────────────────────

def test_submit_puts_post_on_review_and_calls_admin(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                    headers=auth(crew["editor"]))
    assert r.status_code == 200, r.text
    assert post_status(post["id"]) == "on_review"

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT message FROM notifications WHERE user_id=%s AND type='review_requested'",
        (crew["admin_id"],),
    )
    notes = c.fetchall()
    conn.close()
    assert notes, "администратор не узнал, что его ждут"
    assert post["title"] in notes[-1]["message"]


def test_editor_cannot_approve_own_post(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/approve",
                    headers=auth(crew["editor"]))
    assert r.status_code == 403
    assert post_status(post["id"]) == "on_review"


def test_approved_post_without_date_goes_straight_to_queue(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/approve",
                    headers=auth(crew["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "publishing"
    assert r.json()["job"] is not None

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT state FROM publish_jobs WHERE post_id=%s", (post["id"],))
    job = c.fetchone()
    conn.close()
    assert job and job["state"] == "queued"


def test_approved_post_with_future_date_goes_to_schedule(client, crew):
    """
    Намерение автора уже записано в самом посте: стоит дата — значит в
    расписание. Отдельной колонки «что хотел автор» нет сознательно.
    """
    post = make_post(client, crew["editor"], crew["gid"], scheduled_at="2027-06-01T12:00")
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/approve",
                    headers=auth(crew["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"
    assert r.json()["job"] is None
    assert post_status(post["id"]) == "scheduled"


def test_approved_post_with_past_date_is_not_scheduled_into_the_past(client, crew):
    """Просроченная дата не должна отправлять пост в расписание — там он завис бы."""
    post = make_post(client, crew["editor"], crew["gid"], scheduled_at="2020-01-01T12:00")
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/approve",
                    headers=auth(crew["admin"]))
    assert r.json()["status"] == "publishing"


def test_reject_returns_post_with_a_reason(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    r = client.post(
        f"/api/groups/{crew['gid']}/posts/{post['id']}/reject",
        json={"comment": "Уточните дату мероприятия"},
        headers=auth(crew["admin"]),
    )
    assert r.status_code == 200, r.text
    assert post_status(post["id"]) == "draft"

    got = client.get(f"/api/groups/{crew['gid']}/posts/{post['id']}",
                     headers=auth(crew["editor"])).json()
    assert got["review_comment"] == "Уточните дату мероприятия"

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT message FROM notifications WHERE user_id=%s AND type='review_rejected'",
        (crew["editor_id"],),
    )
    notes = c.fetchall()
    conn.close()
    assert notes and "Уточните дату" in notes[-1]["message"]


def test_reject_without_a_reason_is_refused(client, crew):
    """«Доработайте» без объяснения не говорит автору ничего."""
    post = make_post(client, crew["editor"], crew["gid"])
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/reject",
                    json={"comment": "   "}, headers=auth(crew["admin"]))
    assert r.status_code == 400
    assert post_status(post["id"]) == "on_review"


def test_approving_a_post_that_is_not_on_review_is_refused(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/approve",
                    headers=auth(crew["admin"]))
    assert r.status_code == 409


def test_resubmitting_clears_the_previous_verdict(client, crew):
    """Замечание относится к прошлой редакции — висеть на новой оно не должно."""
    post = make_post(client, crew["editor"], crew["gid"])
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/reject",
                json={"comment": "мало деталей"}, headers=auth(crew["admin"]))
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    got = client.get(f"/api/groups/{crew['gid']}/posts/{post['id']}",
                     headers=auth(crew["editor"])).json()
    assert got["review_comment"] is None
    assert got["status"] == "on_review"


# ── Планировщик не должен видеть посты на согласовании ──────────────────────

def test_scheduler_ignores_posts_on_review(client, crew):
    """
    Пост на согласовании с давно прошедшей датой не должен уйти сам. Иначе
    согласование обходилось бы простым ожиданием.
    """
    import scheduler

    post = make_post(client, crew["editor"], crew["gid"], scheduled_at="2020-01-01T12:00")
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))

    conn = get_db()
    try:
        claimed = scheduler.claim_due_post(conn)
    finally:
        conn.close()
    assert claimed is None or claimed["id"] != post["id"]
    assert post_status(post["id"]) == "on_review"


# ── След в журнале ──────────────────────────────────────────────────────────

def test_review_decisions_land_in_the_audit_log(client, crew):
    post = make_post(client, crew["editor"], crew["gid"])
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/submit",
                headers=auth(crew["editor"]))
    client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/reject",
                json={"comment": "поправьте заголовок"}, headers=auth(crew["admin"]))

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT action, details FROM audit_log WHERE object_type='post' AND object_id=%s "
        "ORDER BY id",
        (post["id"],),
    )
    rows = c.fetchall()
    conn.close()
    actions = [r["action"] for r in rows]
    assert "post.submitted" in actions
    assert "post.rejected" in actions
    rejected = next(r for r in rows if r["action"] == "post.rejected")
    assert rejected["details"]["замечание"] == "поправьте заголовок"


# ── Наблюдатель в согласование не вмешивается ───────────────────────────────

def test_volunteer_cannot_touch_review(client, crew, make_user):
    watcher, _ = make_user("watcher")
    add_member(client, crew["admin"], crew["gid"], watcher, "volunteer")
    post = make_post(client, crew["editor"], crew["gid"])
    for path in ("submit", "approve", "reject"):
        r = client.post(f"/api/groups/{crew['gid']}/posts/{post['id']}/{path}",
                        json={"comment": "нет"}, headers=auth(watcher))
        assert r.status_code == 403, path
