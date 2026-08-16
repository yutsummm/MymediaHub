"""
JSON лежит в jsonb, а не в TEXT.

Раньше platforms, tags, media и tg_message_ids были строками: приложение само
делало json.dumps на запись и json.loads на чтение, а база видела просто текст.
Отсюда фильтры вида `platforms LIKE '%"vk"%'` — их нельзя ни проиндексировать,
ни написать безопасно: такой шаблон совпадёт и с подстрокой внутри чужого
значения.
"""
import pytest
from conftest import auth

from utils import get_db

JSON_COLUMNS = [
    ("posts", "platforms"),
    ("posts", "tags"),
    ("posts", "media"),
    ("posts", "tg_message_ids"),
    ("volunteer_media", "media"),
    ("templates", "fields"),
]


def column_type(table: str, column: str) -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    row = c.fetchone()
    conn.close()
    return row["data_type"] if row else ""


# ── Тип и индексы ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("table,column", JSON_COLUMNS)
def test_columns_are_jsonb(table, column):
    assert column_type(table, column) == "jsonb", f"{table}.{column} всё ещё не jsonb"


def test_filters_have_indexes():
    """
    Ради этого перевод и делался: фильтр по площадке идёт по индексу, а не
    перебором всех строк с LIKE.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT indexdef FROM pg_indexes WHERE tablename='posts'")
    defs = " ".join(r["indexdef"] for r in c.fetchall())
    conn.close()
    assert "gin" in defs.lower()
    assert "platforms" in defs and "tags" in defs


def test_query_plan_uses_the_index():
    """Проверяем не наличие индекса, а что планировщик и правда им пользуется."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SET enable_seqscan = off")
    c.execute("EXPLAIN SELECT id FROM posts WHERE platforms ? 'vk'")
    plan = " ".join(r["QUERY PLAN"] for r in c.fetchall())
    c.execute("SET enable_seqscan = on")
    conn.close()
    assert "ix_posts_platforms" in plan, plan


# ── Поведение ────────────────────────────────────────────────────────────────

def test_lists_come_back_as_lists(client, group_with_post):
    token, gid = group_with_post["token"], group_with_post["group_id"]
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Списки", "content": "т", "platforms": ["vk", "telegram"],
              "tags": ["новости", "мероприятия"]},
        headers=auth(token),
    ).json()
    assert created["platforms"] == ["vk", "telegram"]
    assert created["tags"] == ["новости", "мероприятия"]
    assert isinstance(created["media"], list)
    assert isinstance(created["tg_message_ids"], list)


def test_stored_value_is_a_real_json_array(client, group_with_post):
    """psycopg2 отдаёт jsonb готовым списком — строки в колонке больше нет."""
    token, gid = group_with_post["token"], group_with_post["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Хранение", "content": "т", "platforms": ["vk"], "tags": ["тег"]},
        headers=auth(token),
    ).json()["id"]

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT platforms, tags FROM posts WHERE id=%s", (pid,))
    row = c.fetchone()
    conn.close()
    assert row["platforms"] == ["vk"]
    assert row["tags"] == ["тег"]


def test_filter_matches_whole_values_only(client, group_with_post):
    """
    Главная поломка старого способа: LIKE '%"vk"%' совпал бы с подстрокой.
    Тег «vk-новости» не должен находиться по фильтру «vk».
    """
    token, gid = group_with_post["token"], group_with_post["group_id"]
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Похожий тег", "content": "т", "platforms": [], "tags": ["vk-новости"]},
        headers=auth(token),
    )
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Точный тег", "content": "т", "platforms": [], "tags": ["vk"]},
        headers=auth(token),
    )

    found = client.get(f"/api/groups/{gid}/posts?tag=vk", headers=auth(token)).json()
    titles = [p["title"] for p in found["posts"]]
    assert "Точный тег" in titles
    assert "Похожий тег" not in titles, "фильтр не должен цепляться за подстроку"


def test_platform_filter_works(client, group_with_post):
    token, gid = group_with_post["token"], group_with_post["group_id"]
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Только ВК", "content": "т", "platforms": ["vk"]},
        headers=auth(token),
    )
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Только Телеграм", "content": "т", "platforms": ["telegram"]},
        headers=auth(token),
    )
    vk = client.get(f"/api/groups/{gid}/posts?platform=vk", headers=auth(token)).json()
    titles = [p["title"] for p in vk["posts"]]
    assert "Только ВК" in titles
    assert "Только Телеграм" not in titles


def test_empty_lists_survive_the_round_trip(client, group_with_post):
    token, gid = group_with_post["token"], group_with_post["group_id"]
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Пусто", "content": "т", "platforms": [], "tags": []},
        headers=auth(token),
    ).json()
    assert created["platforms"] == []
    assert created["tags"] == []

    fetched = client.get(
        f"/api/groups/{gid}/posts/{created['id']}", headers=auth(token)
    ).json()
    assert fetched["platforms"] == []


def test_telegram_message_ids_are_matched_exactly(client, group_with_post):
    """
    Тот же случай для tg_message_ids: раньше поиск шёл через LIKE, и апдейт про
    сообщение 12 совпадал с постом, где лежит 123 — это отсеивалось разбором
    списка уже в Python.
    """
    from psycopg2.extras import Json

    token, gid = group_with_post["token"], group_with_post["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Сообщения", "content": "т", "platforms": []},
        headers=auth(token),
    ).json()["id"]

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET tg_message_ids=%s WHERE id=%s", (Json([123]), pid))
    conn.commit()
    c.execute("SELECT id FROM posts WHERE tg_message_ids @> %s", (Json([12]),))
    assert c.fetchone() is None, "12 не должно совпасть со 123"
    c.execute("SELECT id FROM posts WHERE tg_message_ids @> %s", (Json([123]),))
    assert c.fetchone()["id"] == pid
    conn.close()


def test_templates_fields_still_parse(client, admin_token):
    """Шаблоны тоже переехали на jsonb — их поля должны читаться как раньше."""
    templates = client.get("/api/templates", headers=auth(admin_token)).json()
    assert templates
    assert all(isinstance(t["fields"], list) for t in templates)
    assert all(isinstance(f, dict) for t in templates for f in t["fields"])
