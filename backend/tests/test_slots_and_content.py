"""
Очередь по расписанию, UTM-метки, переменные группы и автоснятие постов.

Что здесь стережётся:

* **Очередь не назначает двум постам одно окно.** Два поста в одну минуту не
  были бы двумя записями подряд — они перебили бы друг друга в ленте.
* **Очередь считает время на сервере.** Смысл расписания в том, что правила
  живут в одном месте; клиент, вычисляющий дату сам, — это вторая копия
  правил, которая однажды разойдётся с первой.
* **UTM не переписывает чужую разметку** и не попадает в хранимый текст.
* **Неизвестная переменная остаётся видимой**: молча вырезанная подстановка
  уходит в паблик как оговорка автора.
* **Снятый пост остаётся у нас.** Из ленты исчезает запись, а не факт
  публикации: в отчёте за период пост обязан посчитаться.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from conftest import auth

import content
from utils import app_now, get_db


def make_group(client, token: str) -> int:
    r = client.post("/api/groups", json={"name": f"Группа {uuid.uuid4().hex[:6]}"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    # Согласование в этих тестах не при чём — оно проверяется отдельно.
    client.put(f"/api/groups/{r.json()['id']}", json={"require_approval": False},
               headers=auth(token))
    return r.json()["id"]


def make_post(client, token: str, gid: int, **fields) -> dict:
    payload = {"title": f"Пост {uuid.uuid4().hex[:6]}", "content": "текст", "status": "draft"}
    payload.update(fields)
    r = client.post(f"/api/groups/{gid}/posts", json=payload, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def set_slots(client, token: str, gid: int, slots: list[dict]):
    r = client.put(f"/api/groups/{gid}/slots", json={"slots": slots}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["slots"]


ALL_WEEK = [{"weekday": d, "at": "12:00"} for d in range(7)]


@pytest.fixture()
def group(client, make_user):
    token, uid = make_user("slots")
    return {"token": token, "user_id": uid, "gid": make_group(client, token)}


# ── Расписание ──────────────────────────────────────────────────────────────

def test_slots_are_replaced_wholesale_and_sorted(client, group):
    got = set_slots(client, group["token"], group["gid"],
                    [{"weekday": 2, "at": "18:30"}, {"weekday": 0, "at": "09:00"}])
    assert [(s["weekday"], s["at"]) for s in got] == [(0, "09:00"), (2, "18:30")]
    assert got[0]["weekday_label"] == "понедельник"

    # Замена целиком: прежние слоты не накапливаются
    got = set_slots(client, group["token"], group["gid"], [{"weekday": 4, "at": "10:00"}])
    assert [(s["weekday"], s["at"]) for s in got] == [(4, "10:00")]


def test_duplicate_slot_is_not_two_places(client, group):
    """Повтор — опечатка, а не «два поста в это время»."""
    got = set_slots(client, group["token"], group["gid"],
                    [{"weekday": 1, "at": "12:00"}, {"weekday": 1, "at": "12:00"}])
    assert len(got) == 1


def test_bad_slot_is_refused(client, group):
    for bad in ({"weekday": 9, "at": "12:00"}, {"weekday": 1, "at": "четверг"}):
        r = client.put(f"/api/groups/{group['gid']}/slots", json={"slots": [bad]},
                       headers=auth(group["token"]))
        assert r.status_code == 400, bad


def test_only_admin_changes_the_schedule(client, group, make_user):
    editor, _ = make_user("slots-editor")
    link = client.post(f"/api/groups/{group['gid']}/invites",
                       json={"role": "editor", "expires_hours": 24},
                       headers=auth(group["token"])).json()
    client.post(f"/api/invites/{link['token']}/accept", headers=auth(editor))
    r = client.put(f"/api/groups/{group['gid']}/slots", json={"slots": ALL_WEEK},
                   headers=auth(editor))
    assert r.status_code == 403


# ── Очередь ─────────────────────────────────────────────────────────────────

def test_queue_takes_the_next_slot(client, group):
    set_slots(client, group["token"], group["gid"], ALL_WEEK)
    post = make_post(client, group["token"], group["gid"])
    r = client.post(f"/api/groups/{group['gid']}/posts/{post['id']}/queue",
                    json={}, headers=auth(group["token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled"
    assert body["queued"] is True
    assert body["scheduled_at"].endswith("12:00")
    # Окно всегда в будущем: назначить публикацию на вчера бессмысленно.
    assert datetime.fromisoformat(body["scheduled_at"]) > app_now().replace(tzinfo=None)


def test_queue_does_not_put_two_posts_in_one_window(client, group):
    set_slots(client, group["token"], group["gid"], ALL_WEEK)
    times = []
    for _ in range(3):
        post = make_post(client, group["token"], group["gid"])
        r = client.post(f"/api/groups/{group['gid']}/posts/{post['id']}/queue",
                        json={}, headers=auth(group["token"]))
        assert r.status_code == 200, r.text
        times.append(r.json()["scheduled_at"])
    assert len(set(times)) == 3, f"посты столкнулись в одном окне: {times}"
    assert times == sorted(times), "очередь выдала окна не по возрастанию"


def test_queue_respects_manually_scheduled_posts(client, group):
    """
    Окно занято, если на него уже назначен пост — неважно, через очередь или
    вручную. Расписание описывает, когда группа публикует, а не откуда взялась дата.
    """
    set_slots(client, group["token"], group["gid"], ALL_WEEK)
    first = make_post(client, group["token"], group["gid"])
    taken = client.post(f"/api/groups/{group['gid']}/posts/{first['id']}/queue",
                        json={}, headers=auth(group["token"])).json()["scheduled_at"]

    manual = make_post(client, group["token"], group["gid"],
                       status="scheduled", scheduled_at=taken)
    assert manual["scheduled_at"] == taken

    second = make_post(client, group["token"], group["gid"])
    r = client.post(f"/api/groups/{group['gid']}/posts/{second['id']}/queue",
                    json={}, headers=auth(group["token"]))
    assert r.json()["scheduled_at"] != taken


def test_queue_without_a_schedule_says_so(client, group):
    post = make_post(client, group["token"], group["gid"])
    r = client.post(f"/api/groups/{group['gid']}/posts/{post['id']}/queue",
                    json={}, headers=auth(group["token"]))
    assert r.status_code == 409
    assert "расписание" in r.json()["detail"].lower()


def test_queue_refuses_a_published_post(client, group):
    set_slots(client, group["token"], group["gid"], ALL_WEEK)
    post = make_post(client, group["token"], group["gid"])
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET status='published', published_at=NOW() WHERE id=%s", (post["id"],))
    conn.commit()
    conn.close()
    r = client.post(f"/api/groups/{group['gid']}/posts/{post['id']}/queue",
                    json={}, headers=auth(group["token"]))
    assert r.status_code == 409


def test_queue_under_approval_takes_a_window_but_does_not_release(client, make_user):
    """
    Там, где нужна виза, очередь занимает окно, но пост в расписание не уходит:
    иначе очередь стала бы способом опубликоваться в обход согласования.
    """
    admin, _ = make_user("q-admin")
    editor, _ = make_user("q-editor")
    gid = client.post("/api/groups", json={"name": f"Виза {uuid.uuid4().hex[:6]}"},
                      headers=auth(admin)).json()["id"]
    link = client.post(f"/api/groups/{gid}/invites", json={"role": "editor", "expires_hours": 24},
                       headers=auth(admin)).json()
    client.post(f"/api/invites/{link['token']}/accept", headers=auth(editor))
    set_slots(client, admin, gid, ALL_WEEK)

    post = make_post(client, editor, gid)
    r = client.post(f"/api/groups/{gid}/posts/{post['id']}/queue", json={}, headers=auth(editor))
    assert r.status_code == 200, r.text
    assert r.json()["queued"] is False
    assert r.json()["status"] == "draft"
    assert r.json()["scheduled_at"] is not None


def test_next_slot_preview_matches_what_queue_assigns(client, group):
    set_slots(client, group["token"], group["gid"], ALL_WEEK)
    preview = client.get(f"/api/groups/{group['gid']}/slots/next",
                         headers=auth(group["token"])).json()["at"]
    post = make_post(client, group["token"], group["gid"])
    assigned = client.post(f"/api/groups/{group['gid']}/posts/{post['id']}/queue",
                           json={}, headers=auth(group["token"])).json()["scheduled_at"]
    assert preview == assigned


# ── UTM и переменные ────────────────────────────────────────────────────────

def test_utm_marks_links_per_platform():
    text = "Записаться: https://example.ru/reg"
    vk = content.apply_utm(text, "vk", ["мероприятия"])
    tg = content.apply_utm(text, "telegram", ["мероприятия"])
    assert "utm_source=vk" in vk
    assert "utm_source=telegram" in tg
    assert "utm_medium=social" in vk


def test_utm_does_not_overwrite_existing_marks():
    """Ссылка из рекламного кабинета уже размечена — перебить её значит потерять данные."""
    text = "https://example.ru/?utm_source=ads&utm_campaign=vesna"
    assert content.apply_utm(text, "vk", ["x"]) == text


def test_utm_keeps_trailing_punctuation_out_of_the_link():
    out = content.apply_utm("Смотрите https://example.ru.", "vk", None)
    assert out.endswith(".")
    assert "example.ru?" in out or "example.ru/?" in out


def test_unknown_variable_stays_visible():
    """Молча вырезанная подстановка уходит в паблик как оговорка автора."""
    out = content.apply_variables("Мы в {{центр}} на {{адрес}}", {"центр": "«Спектре»"})
    assert "«Спектре»" in out
    assert "{{адрес}}" in out


def test_variables_are_substituted_before_utm():
    """Значение переменной вполне может само быть ссылкой — её тоже надо разметить."""
    out = content.prepare(
        "Сайт: {{сайт}}", platform="vk",
        variables={"сайт": "https://example.ru"}, tags=["новости"], utm_enabled=True,
    )
    assert "utm_source=vk" in out


def test_stored_text_is_untouched_by_marks(client, group):
    """
    Хранимый текст — это то, что человек написал. Метки зависят от площадки и
    в один текст всё равно не помещаются.
    """
    client.put(f"/api/groups/{group['gid']}", json={"utm_enabled": True},
               headers=auth(group["token"]))
    post = make_post(client, group["token"], group["gid"], content="Ссылка https://example.ru")
    got = client.get(f"/api/groups/{group['gid']}/posts/{post['id']}",
                     headers=auth(group["token"])).json()
    assert got["content"] == "Ссылка https://example.ru"
    assert "utm_" not in got["content"]


def test_group_keeps_variables_and_hashtag_sets(client, group):
    r = client.put(
        f"/api/groups/{group['gid']}",
        json={"variables": {"центр": "«Спектр»", "адрес": "пр. Мира, 1"},
              "hashtag_sets": [{"name": "мероприятия", "tags": "#молодёжь #красноярск"}]},
        headers=auth(group["token"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["variables"]["центр"] == "«Спектр»"
    assert r.json()["hashtag_sets"][0]["name"] == "мероприятия"


# ── Автоснятие ──────────────────────────────────────────────────────────────

def test_removed_post_still_counts_as_published(client, group):
    """
    Из ленты исчезает запись, а не факт публикации: пост набрал просмотры и в
    отчёте за период обязан посчитаться.
    """
    post = make_post(client, group["token"], group["gid"])
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET status='published', published_at=NOW(), removed_at=NOW() "
              "WHERE id=%s", (post["id"],))
    conn.commit()
    conn.close()

    summary = client.get(f"/api/groups/{group['gid']}/analytics/summary",
                         headers=auth(group["token"])).json()
    assert summary["published"] == 1


def test_retention_takes_only_posts_whose_time_has_come(client, group, monkeypatch):
    import retention

    due = make_post(client, group["token"], group["gid"])
    later = make_post(client, group["token"], group["gid"])
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET status='published', published_at=NOW(), auto_delete_at=%s, "
              "vk_post_id='777' WHERE id=%s", (app_now() - timedelta(hours=1), due["id"]))
    c.execute("UPDATE posts SET status='published', published_at=NOW(), auto_delete_at=%s, "
              "vk_post_id='888' WHERE id=%s", (app_now() + timedelta(days=3), later["id"]))
    conn.commit()

    seen: list[str] = []

    def fake_remove(conn_, post):
        seen.append(str(post["vk_post_id"]))
        return []

    monkeypatch.setattr(retention, "remove_post", fake_remove)
    retention.process_due()

    assert seen == ["777"], f"снято не то: {seen}"
    c.execute("SELECT removed_at FROM posts WHERE id=%s", (due["id"],))
    assert c.fetchone()["removed_at"] is not None
    c.execute("SELECT removed_at FROM posts WHERE id=%s", (later["id"],))
    assert c.fetchone()["removed_at"] is None
    conn.close()


def test_failed_removal_is_retried_next_tick(client, group, monkeypatch):
    """
    Не сняли — значит запись всё ещё висит, и повторить попытку правильно.
    Отметку `removed_at` в этом случае ставить нельзя: она означала бы, что
    из ленты убрали, хотя не убрали.
    """
    import retention

    post = make_post(client, group["token"], group["gid"])
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET status='published', published_at=NOW(), auto_delete_at=%s, "
              "vk_post_id='999' WHERE id=%s", (app_now() - timedelta(hours=1), post["id"]))
    conn.commit()

    monkeypatch.setattr(retention, "remove_post", lambda conn_, p: ["ВКонтакте: нет доступа"])
    retention.process_due()

    c.execute("SELECT removed_at, remove_error FROM posts WHERE id=%s", (post["id"],))
    row = c.fetchone()
    assert row["removed_at"] is None
    assert "нет доступа" in row["remove_error"]
    conn.close()


# ── История поста ───────────────────────────────────────────────────────────

def test_history_shows_the_whole_path(client, make_user):
    admin, _ = make_user("hist-admin")
    editor, _ = make_user("hist-editor")
    gid = client.post("/api/groups", json={"name": f"Ист {uuid.uuid4().hex[:6]}"},
                      headers=auth(admin)).json()["id"]
    link = client.post(f"/api/groups/{gid}/invites", json={"role": "editor", "expires_hours": 24},
                       headers=auth(admin)).json()
    client.post(f"/api/invites/{link['token']}/accept", headers=auth(editor))

    post = make_post(client, editor, gid)
    client.post(f"/api/groups/{gid}/posts/{post['id']}/submit", headers=auth(editor))
    client.post(f"/api/groups/{gid}/posts/{post['id']}/reject",
                json={"comment": "нужен адрес"}, headers=auth(admin))

    events = client.get(f"/api/posts/{post['id']}/history", headers=auth(editor)).json()["events"]
    actions = [e["action"] for e in events]
    assert actions[0] == "created"
    assert "post.submitted" in actions
    assert "post.rejected" in actions
    rejected = next(e for e in events if e["action"] == "post.rejected")
    assert rejected["details"] == "нужен адрес"
    assert rejected["actor"], "непонятно, кто вернул пост"


def test_history_is_closed_to_outsiders(client, group, make_user):
    stranger, _ = make_user("hist-stranger")
    post = make_post(client, group["token"], group["gid"])
    r = client.get(f"/api/posts/{post['id']}/history", headers=auth(stranger))
    assert r.status_code == 403


# ── Стык: то, что реально уходит в соцсеть ──────────────────────────────────

def test_published_text_carries_variables_and_marks(client, group, monkeypatch):
    """
    Самое важное место: подстановки и метки применяются на выпуске, и проверять
    их надо там, где текст уходит наружу, а не только в чистой функции.
    """
    import publishing
    import utils

    gid, token = group["gid"], group["token"]
    client.put(f"/api/groups/{gid}", json={
        "utm_enabled": True, "variables": {"центр": "МЦ «Спектр»"},
    }, headers=auth(token))

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO vk_settings (workspace_id, group_id, access_token) VALUES (%s,'42','tkn') "
        "ON CONFLICT DO NOTHING", (gid,))
    conn.commit()

    post = make_post(client, token, gid,
                     content="Ждём в {{центр}}. Запись: https://example.ru/reg",
                     tags=["мероприятия"], platforms=["vk"])

    sent: dict = {}

    def fake_wall_post(token_, group_id, message, attachments=None):
        sent["message"] = message
        return 555

    monkeypatch.setattr(publishing, "vk_wall_post", fake_wall_post)
    monkeypatch.setattr(utils, "vk_wall_post", fake_wall_post, raising=False)

    c.execute("SELECT * FROM posts WHERE id=%s", (post["id"],))
    publishing.perform_publish(conn, c.fetchone(), group_id=gid)
    conn.close()

    assert "МЦ «Спектр»" in sent["message"], "подстановка не применилась на выпуске"
    assert "{{центр}}" not in sent["message"]
    assert "utm_source=vk" in sent["message"], "ссылка ушла без меток"


def test_group_without_marks_publishes_plain_text(client, group, monkeypatch):
    """Выключенные метки означают выключенные метки, а не «почти выключенные»."""
    import publishing

    gid, token = group["gid"], group["token"]
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO vk_settings (workspace_id, group_id, access_token) VALUES (%s,'42','tkn') "
        "ON CONFLICT DO NOTHING", (gid,))
    conn.commit()

    post = make_post(client, token, gid, content="Ссылка https://example.ru", platforms=["vk"])
    sent: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post",
                        lambda *a, **kw: (sent.update(message=a[2]), 556)[1])

    c.execute("SELECT * FROM posts WHERE id=%s", (post["id"],))
    publishing.perform_publish(conn, c.fetchone(), group_id=gid)
    conn.close()
    # В ВК уходит заголовок вместе с текстом — сверяем именно ссылку.
    assert "https://example.ru" in sent["message"]
    assert "utm_" not in sent["message"]
