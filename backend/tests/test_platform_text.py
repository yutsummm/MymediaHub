"""
Свой текст под площадку и первый комментарий.

Что стережётся:

* **Переопределение работает и не портит остальное.** Свой текст для Telegram
  не должен утечь во ВКонтакте, а его отсутствие обязано означать «как было»:
  посты, написанные до появления переопределений, менять поведение не должны.
* **Пустое переопределение — это отсутствие переопределения.** «Я стёр текст
  для Telegram» означает «верните общий», а не «опубликуйте там пустоту».
* **Первый комментарий уходит после записи и не отменяет её.** Запись уже на
  стене; откатывать публикацию из-за не оставленного комментария бессмысленно,
  но и промолчать об ошибке нельзя.
* **Подстановки и метки применяются и к тексту площадки, и к комментарию.**
  Ссылка на регистрацию как раз в комментарии и живёт — не разметить её
  значило бы потерять ровно те переходы, ради которых всё затевалось.
"""
import uuid

import pytest
from conftest import auth

import content
from utils import get_db


def make_group(client, token: str) -> int:
    r = client.post("/api/groups", json={"name": f"Группа {uuid.uuid4().hex[:6]}"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    client.put(f"/api/groups/{gid}", json={"require_approval": False}, headers=auth(token))
    return gid


def make_post(client, token: str, gid: int, **fields) -> dict:
    payload = {"title": f"Пост {uuid.uuid4().hex[:6]}", "content": "общий текст",
               "status": "draft", "platforms": ["vk", "telegram"]}
    payload.update(fields)
    r = client.post(f"/api/groups/{gid}/posts", json=payload, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def connect_vk(gid: int) -> None:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO vk_settings (workspace_id, group_id, access_token) "
        "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (gid,))
    conn.commit()
    conn.close()


@pytest.fixture()
def group(client, make_user):
    token, uid = make_user("platform")
    gid = make_group(client, token)
    connect_vk(gid)
    return {"token": token, "gid": gid, "user_id": uid}


def publish(conn, post_id: int, gid: int):
    import publishing

    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    return publishing.perform_publish(conn, c.fetchone(), group_id=gid)


# ── Выбор текста ────────────────────────────────────────────────────────────

def test_platform_text_falls_back_to_the_common_one():
    post = {"content": "общий", "content_overrides": {}}
    assert content.for_platform(post, "telegram") == "общий"
    assert content.for_platform(post, "vk") == "общий"


def test_platform_text_uses_the_override():
    post = {"content": "общий", "content_overrides": {"telegram": "для телеги"}}
    assert content.for_platform(post, "telegram") == "для телеги"
    # Чужое переопределение не должно утечь на соседнюю площадку
    assert content.for_platform(post, "vk") == "общий"


def test_blank_override_means_no_override():
    """«Стёр текст для Telegram» — это «верните общий», а не «опубликуйте пустоту»."""
    for blank in ("", "   ", "\n"):
        post = {"content": "общий", "content_overrides": {"telegram": blank}}
        assert content.for_platform(post, "telegram") == "общий", repr(blank)


def test_broken_overrides_do_not_break_publishing():
    """В колонке может оказаться не то, что мы ждали, — падать из-за этого нельзя."""
    for junk in (None, "строка", ["список"], 42):
        assert content.for_platform({"content": "общий", "content_overrides": junk}, "vk") == "общий"


# ── Хранение ────────────────────────────────────────────────────────────────

def test_override_survives_a_round_trip(client, group):
    post = make_post(client, group["token"], group["gid"],
                     content_overrides={"telegram": "Коротко для канала"})
    got = client.get(f"/api/groups/{group['gid']}/posts/{post['id']}",
                     headers=auth(group["token"])).json()
    assert got["content_overrides"] == {"telegram": "Коротко для канала"}
    assert got["content"] == "общий текст"


def test_clearing_an_override_removes_it(client, group):
    post = make_post(client, group["token"], group["gid"],
                     content_overrides={"telegram": "Коротко"})
    client.put(f"/api/groups/{group['gid']}/posts/{post['id']}",
               json={"content_overrides": {"telegram": "   "}}, headers=auth(group["token"]))
    got = client.get(f"/api/groups/{group['gid']}/posts/{post['id']}",
                     headers=auth(group["token"])).json()
    assert got["content_overrides"] == {}


def test_first_comment_survives_a_round_trip(client, group):
    post = make_post(client, group["token"], group["gid"],
                     first_comment="Записаться: https://example.ru/reg")
    got = client.get(f"/api/groups/{group['gid']}/posts/{post['id']}",
                     headers=auth(group["token"])).json()
    assert got["first_comment"] == "Записаться: https://example.ru/reg"


# ── Выпуск ──────────────────────────────────────────────────────────────────

def test_each_platform_gets_its_own_text(client, group, monkeypatch):
    import publishing
    import utils

    post = make_post(client, group["token"], group["gid"],
                     content="Текст для ВК", content_overrides={"telegram": "Текст для канала"})
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO tg_settings (workspace_id, bot_token, chat_id) "
              "VALUES (%s,'tkn','@chan') ON CONFLICT DO NOTHING", (group["gid"],))
    conn.commit()

    sent: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post",
                        lambda *a, **kw: (sent.update(vk=a[2]), 11)[1])
    monkeypatch.setattr(publishing, "tg_send_post",
                        lambda *a, **kw: (sent.update(tg=a[2]), [22])[1])
    monkeypatch.setattr(utils, "vk_wall_post", lambda *a, **kw: 11, raising=False)

    publish(conn, post["id"], group["gid"])
    conn.close()

    assert "Текст для ВК" in sent["vk"]
    assert "Текст для канала" in sent["tg"]
    assert "Текст для канала" not in sent["vk"], "текст Telegram утёк во ВКонтакте"


def test_first_comment_goes_under_the_post(client, group, monkeypatch):
    import publishing

    post = make_post(client, group["token"], group["gid"], platforms=["vk"],
                     first_comment="Записаться: https://example.ru/reg")
    conn = get_db()
    left: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post", lambda *a, **kw: 777)
    monkeypatch.setattr(
        publishing, "vk_wall_create_comment",
        lambda token, gid_, post_id, message: (left.update(post_id=post_id, text=message), 99)[1])

    publish(conn, post["id"], group["gid"])
    c = conn.cursor()
    c.execute("SELECT vk_comment_id FROM posts WHERE id=%s", (post["id"],))
    stored = c.fetchone()["vk_comment_id"]
    conn.close()

    assert left["post_id"] == 777, "комментарий ушёл не под ту запись"
    assert "example.ru/reg" in left["text"]
    assert stored == "99", "не запомнили, что именно оставили под записью"


def test_first_comment_gets_marks_too(client, group, monkeypatch):
    """
    Ссылка на регистрацию как раз в комментарии и живёт: не разметить её
    значило бы потерять ровно те переходы, ради которых приём и придуман.
    """
    import publishing

    client.put(f"/api/groups/{group['gid']}",
               json={"utm_enabled": True, "variables": {"центр": "МЦ «Спектр»"}},
               headers=auth(group["token"]))
    post = make_post(client, group["token"], group["gid"], platforms=["vk"], tags=["мероприятия"],
                     first_comment="Запись в {{центр}}: https://example.ru/reg")
    conn = get_db()
    left: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post", lambda *a, **kw: 778)
    monkeypatch.setattr(publishing, "vk_wall_create_comment",
                        lambda t, g, p, message: (left.update(text=message), 100)[1])
    publish(conn, post["id"], group["gid"])
    conn.close()

    assert "МЦ «Спектр»" in left["text"]
    assert "utm_source=vk" in left["text"]


def test_no_comment_means_no_call(client, group, monkeypatch):
    import publishing

    post = make_post(client, group["token"], group["gid"], platforms=["vk"])
    conn = get_db()
    calls: list = []
    monkeypatch.setattr(publishing, "vk_wall_post", lambda *a, **kw: 779)
    def record(*a, **kw):
        calls.append(a)
        return 1

    monkeypatch.setattr(publishing, "vk_wall_create_comment", record)
    publish(conn, post["id"], group["gid"])
    conn.close()
    assert calls == [], "лезли в ВК за комментарием, которого нет"


def test_failed_comment_does_not_undo_the_post(client, group, monkeypatch):
    """
    Запись уже на стене. Откатывать публикацию из-за не оставленного
    комментария бессмысленно — но и промолчать нельзя.
    """
    import publishing

    post = make_post(client, group["token"], group["gid"], platforms=["vk"],
                     first_comment="Записаться: https://example.ru")
    conn = get_db()
    monkeypatch.setattr(publishing, "vk_wall_post", lambda *a, **kw: 780)

    def boom(*a, **kw):
        raise ValueError("Access denied: no access to comment")

    monkeypatch.setattr(publishing, "vk_wall_create_comment", boom)
    result = publish(conn, post["id"], group["gid"])

    c = conn.cursor()
    c.execute("SELECT status, vk_post_id, vk_comment_id FROM posts WHERE id=%s", (post["id"],))
    row = c.fetchone()
    conn.close()

    assert row["status"] == "published"
    assert row["vk_post_id"] == "780"
    assert row["vk_comment_id"] is None
    problems = " ".join(result.get("vk_photo_errors") or [])
    assert "комментарий" in problems, "об ошибке комментария нигде не сказано"
