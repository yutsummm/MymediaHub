"""
Обращения под публикациями, срок ответа и подсказки о начале работы.

Главное, что здесь стережётся, — **правило «отвечено»**. Оно единственное в
этой части неточное: комментарий сообщества без указания адресата мы считаем
ответом на всё, что было под записью до него. Правило выбрано под то, как
люди отвечают на самом деле, но ошибаться оно обязано предсказуемо:

* молчание не закрывает ничего и никогда;
* адресный ответ закрывает ровно своё обращение;
* повторное вычитывание не сбрасывает уже проставленную отметку — иначе
  очередь оживала бы каждые десять минут.

Отдельно проверяется, что в очередь не попадают наши собственные ответы:
отвечать на них некому, а в отчёт учредителю они попали бы как обращения
жителей — то есть учреждение отчитывалось бы разговором с самим собой.
"""
import uuid
from datetime import timedelta

import pytest
from conftest import auth

import comments as comments_service
import onboarding
from utils import app_now, get_db


def make_group(client, token: str) -> int:
    r = client.post("/api/groups", json={"name": f"Группа {uuid.uuid4().hex[:6]}"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    client.put(f"/api/groups/{gid}", json={"require_approval": False}, headers=auth(token))
    return gid


def make_published_post(client, token: str, gid: int) -> int:
    r = client.post(f"/api/groups/{gid}/posts",
                    json={"title": f"Пост {uuid.uuid4().hex[:6]}", "content": "текст",
                          "status": "draft", "platforms": ["vk"]},
                    headers=auth(token))
    pid = r.json()["id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET status='published', published_at=NOW(), vk_post_id='500' "
              "WHERE id=%s", (pid,))
    conn.commit()
    conn.close()
    return pid


def add_comment(post_id: int, gid: int, external_id: str, *, text="вопрос",
                from_group=False, parent=None, minutes_ago=0, author="Житель"):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO post_comments (post_id, group_id, platform, external_id, "
        "  parent_external_id, author_external_id, author_name, text, created_at, from_group) "
        "VALUES (%s,%s,'vk',%s,%s,'1',%s,%s,%s,%s) RETURNING id",
        (post_id, gid, external_id, parent, author, text,
         app_now() - timedelta(minutes=minutes_ago), from_group),
    )
    cid = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return cid


@pytest.fixture()
def group(client, make_user):
    token, uid = make_user("comments")
    gid = make_group(client, token)
    return {"token": token, "gid": gid, "user_id": uid,
            "post_id": make_published_post(client, token, gid)}


def resolve(post_id: int) -> int:
    conn = get_db()
    try:
        closed = comments_service.resolve_answers(conn, post_id)
        conn.commit()
        return closed
    finally:
        conn.close()


def answered_at(post_id: int, external_id: str):
    """Отметка об ответе. Ищем по паре пост+номер: номер уникален только внутри записи."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT answered_at FROM post_comments WHERE post_id=%s AND external_id=%s",
              (post_id, external_id))
    row = c.fetchone()
    conn.close()
    return row["answered_at"] if row else None


# ── Правило «отвечено» ──────────────────────────────────────────────────────

def test_silence_never_closes_anything(group):
    """Пока сообщество молчит, обращение остаётся открытым — это основа всего."""
    add_comment(group["post_id"], group["gid"], "c1", minutes_ago=600)
    assert resolve(group["post_id"]) == 0
    assert answered_at(group["post_id"], "c1") is None


def test_targeted_reply_closes_only_its_own(group):
    add_comment(group["post_id"], group["gid"], "c1", minutes_ago=60)
    add_comment(group["post_id"], group["gid"], "c2", minutes_ago=50)
    add_comment(group["post_id"], group["gid"], "r1", from_group=True,
                parent="c1", minutes_ago=10, author="Центр")
    resolve(group["post_id"])
    assert answered_at(group["post_id"], "c1") is not None
    assert answered_at(group["post_id"], "c2") is None, "адресный ответ закрыл чужое обращение"


def test_general_reply_closes_what_came_before_it(group):
    """Ответ без адресата — обычный способ ответить, когда вопрос под записью один."""
    add_comment(group["post_id"], group["gid"], "c1", minutes_ago=60)
    add_comment(group["post_id"], group["gid"], "r1", from_group=True,
                minutes_ago=30, author="Центр")
    # Пришло уже после ответа — закрывать нечем
    add_comment(group["post_id"], group["gid"], "c2", minutes_ago=10)
    resolve(group["post_id"])
    assert answered_at(group["post_id"], "c1") is not None
    assert answered_at(group["post_id"], "c2") is None, "ответ закрыл обращение, которого ещё не было"


def test_resolving_twice_does_not_move_the_mark(group):
    """
    Отметку ставим один раз. Иначе повторное вычитывание сдвигало бы время
    ответа вперёд, и среднее в отчёте учредителю становилось бы лучше само
    собой — просто оттого, что мы почаще заглядываем в ВК.
    """
    add_comment(group["post_id"], group["gid"], "c1", minutes_ago=120)
    add_comment(group["post_id"], group["gid"], "r1", from_group=True,
                parent="c1", minutes_ago=90, author="Центр")
    resolve(group["post_id"])
    first = answered_at(group["post_id"], "c1")
    resolve(group["post_id"])
    assert answered_at(group["post_id"], "c1") == first


# ── Очередь ─────────────────────────────────────────────────────────────────

def test_queue_shows_only_citizen_questions(client, group):
    add_comment(group["post_id"], group["gid"], "c1", text="Когда занятия?", minutes_ago=30)
    add_comment(group["post_id"], group["gid"], "r1", from_group=True,
                text="ответ центра", minutes_ago=5, author="Центр")
    r = client.get(f"/api/groups/{group['gid']}/comments", headers=auth(group["token"]))
    assert r.status_code == 200, r.text
    texts = [i["text"] for i in r.json()["items"]]
    assert "ответ центра" not in texts, "свой же ответ попал в очередь обращений"


def test_queue_marks_overdue(client, group):
    """Срок по умолчанию — восемь часов; девятичасовое обращение просрочено."""
    add_comment(group["post_id"], group["gid"], "old", minutes_ago=9 * 60)
    add_comment(group["post_id"], group["gid"], "fresh", minutes_ago=10)
    items = client.get(f"/api/groups/{group['gid']}/comments",
                       headers=auth(group["token"])).json()["items"]
    by_id = {i["text"]: i for i in items}
    old = next(i for i in items if i["minutes_left"] < 0)
    assert old["overdue"] is True
    assert any(i["overdue"] is False for i in items), "свежее обращение помечено просроченным"
    assert by_id  # очередь непуста


def test_queue_orders_oldest_first(client, group):
    add_comment(group["post_id"], group["gid"], "new", text="новое", minutes_ago=5)
    add_comment(group["post_id"], group["gid"], "old", text="старое", minutes_ago=300)
    items = client.get(f"/api/groups/{group['gid']}/comments",
                       headers=auth(group["token"])).json()["items"]
    assert items[0]["text"] == "старое", "сверху должно быть то, у чего срок ближе"


def test_answered_are_hidden_by_default_and_findable_on_request(client, group):
    add_comment(group["post_id"], group["gid"], "c1", text="закрытое", minutes_ago=100)
    add_comment(group["post_id"], group["gid"], "r1", from_group=True,
                parent="c1", minutes_ago=50, author="Центр")
    resolve(group["post_id"])
    pending = client.get(f"/api/groups/{group['gid']}/comments",
                         headers=auth(group["token"])).json()
    assert pending["total"] == 0
    done = client.get(f"/api/groups/{group['gid']}/comments?status=answered",
                      headers=auth(group["token"])).json()
    assert done["total"] == 1
    assert done["items"][0]["minutes_left"] is None, "у отвеченного срок не имеет смысла"


def test_summary_counts_pending_and_overdue(client, group):
    add_comment(group["post_id"], group["gid"], "a", minutes_ago=9 * 60)
    add_comment(group["post_id"], group["gid"], "b", minutes_ago=10)
    s = client.get(f"/api/groups/{group['gid']}/comments/summary",
                   headers=auth(group["token"])).json()
    assert s["pending"] == 2
    assert s["overdue"] == 1
    assert s["sla_hours"] == 8


def test_sla_is_configurable(client, group):
    client.put(f"/api/groups/{group['gid']}", json={"reply_sla_hours": 4},
               headers=auth(group["token"]))
    add_comment(group["post_id"], group["gid"], "a", minutes_ago=5 * 60)
    s = client.get(f"/api/groups/{group['gid']}/comments/summary",
                   headers=auth(group["token"])).json()
    assert s["sla_hours"] == 4
    assert s["overdue"] == 1, "при четырёхчасовом сроке пятичасовое обращение просрочено"


def test_watchers_and_outsiders_do_not_see_the_queue(client, group, make_user):
    stranger, _ = make_user("stranger")
    assert client.get(f"/api/groups/{group['gid']}/comments",
                      headers=auth(stranger)).status_code == 403


# ── Ответ из интерфейса ─────────────────────────────────────────────────────

def test_reply_marks_answered_immediately(client, group, monkeypatch):
    """
    Отметку ставим сразу, не дожидаясь следующего вычитывания: между тактами
    до десяти минут, и всё это время отвеченное висело бы в очереди.
    """
    import routers.comments as router

    cid = add_comment(group["post_id"], group["gid"], "c1", minutes_ago=30)
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (group["gid"],))
    conn.commit()
    conn.close()

    sent: dict = {}
    monkeypatch.setattr(router, "vk_wall_create_comment",
                        lambda t, g, p, msg, reply_to_comment=None:
                        (sent.update(text=msg, to=reply_to_comment), 7)[1])

    r = client.post(f"/api/groups/{group['gid']}/comments/{cid}/reply",
                    json={"text": "Занятия по субботам в 12:00"}, headers=auth(group["token"]))
    assert r.status_code == 200, r.text
    assert sent["to"] == "c1", "ответ ушёл не адресно — человек не поймёт, что отвечают ему"
    assert answered_at(group["post_id"], "c1") is not None

    left = client.get(f"/api/groups/{group['gid']}/comments",
                      headers=auth(group["token"])).json()
    assert left["total"] == 0


def test_empty_reply_is_refused(client, group):
    cid = add_comment(group["post_id"], group["gid"], "c1", minutes_ago=30)
    r = client.post(f"/api/groups/{group['gid']}/comments/{cid}/reply",
                    json={"text": "   "}, headers=auth(group["token"]))
    assert r.status_code == 400


def test_double_reply_is_refused(client, group, monkeypatch):
    import routers.comments as router

    cid = add_comment(group["post_id"], group["gid"], "c1", minutes_ago=30)
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE post_comments SET answered_at=NOW() WHERE id=%s", (cid,))
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (group["gid"],))
    conn.commit()
    conn.close()
    monkeypatch.setattr(router, "vk_wall_create_comment", lambda *a, **kw: 1)
    r = client.post(f"/api/groups/{group['gid']}/comments/{cid}/reply",
                    json={"text": "ещё раз"}, headers=auth(group["token"]))
    assert r.status_code == 409


# ── Сводка для отчёта ───────────────────────────────────────────────────────

def test_stats_ignore_our_own_replies(group):
    """Наши ответы в знаменателе означали бы, что учреждение отвечает само себе."""
    add_comment(group["post_id"], group["gid"], "c1", minutes_ago=100)
    add_comment(group["post_id"], group["gid"], "r1", from_group=True,
                parent="c1", minutes_ago=40, author="Центр")
    resolve(group["post_id"])
    conn = get_db()
    try:
        s = comments_service.stats(conn, group["gid"])
    finally:
        conn.close()
    assert s["total"] == 1
    assert s["answered"] == 1
    assert s["avg_reply_hours"] == 1.0


def test_stats_say_nothing_instead_of_zero_hours(group):
    """«Ни на что не отвечали» и «отвечали мгновенно» — разные вещи."""
    add_comment(group["post_id"], group["gid"], "c1", minutes_ago=100)
    conn = get_db()
    try:
        s = comments_service.stats(conn, group["gid"])
    finally:
        conn.close()
    assert s["answered"] == 0
    assert s["avg_reply_hours"] is None


# ── Начало работы ───────────────────────────────────────────────────────────

def test_onboarding_is_computed_not_remembered(client, group):
    """
    Флаг «уже подключил» умеет разойтись с реальностью. Шаг обязан гаснуть
    сам, когда интеграцию отключают.
    """
    conn = get_db()
    try:
        before = onboarding.progress(conn, group["gid"], "admin")
        assert not any(s["key"] == "network" and s["done"] for s in before["steps"])

        c = conn.cursor()
        c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
                  "VALUES (%s,'42','tkn')", (group["gid"],))
        conn.commit()
        after = onboarding.progress(conn, group["gid"], "admin")
        assert any(s["key"] == "network" and s["done"] for s in after["steps"])

        c.execute("DELETE FROM vk_settings WHERE workspace_id=%s", (group["gid"],))
        conn.commit()
        again = onboarding.progress(conn, group["gid"], "admin")
        assert not any(s["key"] == "network" and s["done"] for s in again["steps"])
    finally:
        conn.close()


def test_onboarding_hides_settings_steps_from_non_admins(client, group):
    """Подсказка «сделайте то, что вам запрещено» — издевательство."""
    conn = get_db()
    try:
        editor_steps = onboarding.progress(conn, group["gid"], "editor")["steps"]
    finally:
        conn.close()
    assert all(s["href"] != "/settings" for s in editor_steps)
    assert any(s["key"] == "post" for s in editor_steps), "редактору нечего показать вовсе"


def test_onboarding_completes_when_the_required_steps_are_done(client, group):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
                  "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (group["gid"],))
        c.execute("INSERT INTO group_members (group_id, user_id, role) "
                  "SELECT %s, id, 'editor' FROM users WHERE id <> %s LIMIT 1 "
                  "ON CONFLICT DO NOTHING", (group["gid"], group["user_id"]))
        conn.commit()
        state = onboarding.progress(conn, group["gid"], "admin")
    finally:
        conn.close()
    assert state["complete"] is True, f"осталось: {[s['key'] for s in state['steps'] if not s['done'] and not s['optional']]}"
    assert state["done"] == state["total"]


def test_onboarding_endpoint_is_closed_to_outsiders(client, group, make_user):
    stranger, _ = make_user("ob-stranger")
    assert client.get(f"/api/groups/{group['gid']}/onboarding",
                      headers=auth(stranger)).status_code == 403


# ── Первое вычитывание ──────────────────────────────────────────────────────

def test_first_pass_stores_history_without_shouting(client, group, monkeypatch):
    """
    При первом вычитывании приходит история за две недели. Предупреждать о
    каждом давно провисевшем обращении значило бы вывалить архив в уведомления
    как новости — администратор перестал бы их читать вообще.

    В очередь такие обращения попадают и помечаются просроченными; там им и
    место.
    """
    import comments as service

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (group["gid"],))
    conn.commit()
    conn.close()

    long_ago = int((app_now() - timedelta(days=3)).timestamp())
    monkeypatch.setattr(service, "vk_get_comments", lambda *a, **kw: {
        "items": [{"id": 900, "from_id": 12, "date": long_ago, "text": "давний вопрос"}],
        "profiles": [{"id": 12, "first_name": "Пётр", "last_name": "И."}],
        "groups": [],
    })

    service.collect()

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT warned_at FROM post_comments WHERE external_id='900'")
    stored = c.fetchone()
    c.execute("SELECT COUNT(*) n FROM notifications WHERE type='comment_due' AND group_id=%s",
              (group["gid"],))
    noise = c.fetchone()["n"]
    conn.close()

    assert stored is not None, "историю вообще не сохранили"
    assert stored["warned_at"] is not None, "давнее обращение оставили под предупреждение"
    assert noise == 0, "первое вычитывание вывалило историю в уведомления"

    # Но в очереди оно есть и честно помечено просроченным
    items = client.get(f"/api/groups/{group['gid']}/comments",
                       headers=auth(group["token"])).json()["items"]
    assert any(i["text"] == "давний вопрос" and i["overdue"] for i in items)


def test_second_pass_warns_as_usual(client, group, monkeypatch):
    """Молчание касается только самого первого прохода, дальше всё как обычно."""
    import comments as service

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (group["gid"],))
    conn.commit()
    conn.close()
    # Группа уже известна сборщику
    add_comment(group["post_id"], group["gid"], "seen", minutes_ago=5)

    stale = int((app_now() - timedelta(hours=7)).timestamp())
    monkeypatch.setattr(service, "vk_get_comments", lambda *a, **kw: {
        "items": [{"id": 901, "from_id": 13, "date": stale, "text": "новый вопрос"}],
        "profiles": [{"id": 13, "first_name": "Анна", "last_name": "К."}],
        "groups": [],
    })
    service.collect()

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) n FROM notifications WHERE type='comment_due' AND group_id=%s",
              (group["gid"],))
    warned = c.fetchone()["n"]
    conn.close()
    assert warned > 0, "о приближении срока никого не предупредили"
