"""
Три вещи, на которых аналитика и поиск спотыкались.

1. Таймлайн делал отдельный запрос на каждый день периода: месяц — 30 обращений
   к базе, квартал — 90, экспорт за произвольный период — сколько попросят.
   Все запросы отличались только датой.
2. Поиск по постам шёл через `LOWER(title) LIKE LOWER(...)`: ни один индекс
   такому выражению не помогает, а спецсимволы шаблона не экранировались —
   запрос «%» находил вообще всё.
3. Вовлечённость делилась на `max(views, 1)`. При нуле просмотров это давало
   либо трёхзначные проценты, либо ровные «0,0 %», которые читаются как
   «людям не заходит», хотя цифр просто нет.
"""
import datetime
import uuid

import pytest
from conftest import auth

from routers.analytics import _avg_views, _engagement, _timeline
from utils import app_now, get_db, like_pattern


class CountingCursor:
    """Курсор, считающий обращения к базе."""

    def __init__(self, cursor):
        self._c = cursor
        self.executes = 0

    def execute(self, *a, **kw):
        self.executes += 1
        return self._c.execute(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._c, name)


def make_published(client, gid: str | int, token: str, when, title=None) -> int:
    """Опубликованный пост с проставленной датой публикации."""
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={
            "title": title or f"Пост {uuid.uuid4().hex[:6]}",
            "content": "текст",
            "status": "published",
            "platforms": ["vk"],
        },
        headers=auth(token),
    ).json()["id"]
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("UPDATE posts SET published_at=%s WHERE id=%s", (when, pid))
        conn.commit()
    finally:
        conn.close()
    return pid


# ── 1. Таймлайн: один запрос вместо запроса на день ─────────────────────────

def test_timeline_makes_one_query_per_call(group_with_post):
    """
    Главное свойство: число обращений к базе не зависит от длины периода.
    Раньше квартал стоил 90 запросов — по одному на день.
    """
    gid = group_with_post["group_id"]
    days = [app_now().replace(hour=12) - datetime.timedelta(days=i)
            for i in range(89, -1, -1)]
    conn = get_db()
    try:
        c = CountingCursor(conn.cursor())
        _timeline(c, "group_id=%s", [gid], days)
    finally:
        conn.close()
    assert c.executes == 1, f"квартал стоил {c.executes} запросов вместо одного"


def test_timeline_keeps_empty_days_and_sums_the_rest(client, group_with_post):
    """
    Ряд должен остаться сплошным: SQL вернёт только дни, где что-то было,
    а графику нужен каждый день периода — иначе он молча съедет.
    """
    gid, token = group_with_post["group_id"], group_with_post["token"]
    today = app_now().replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - datetime.timedelta(days=1)
    make_published(client, gid, token, today)
    make_published(client, gid, token, today)
    make_published(client, gid, token, yesterday)

    days = [today - datetime.timedelta(days=i) for i in range(4, -1, -1)]
    conn = get_db()
    try:
        rows = _timeline(conn.cursor(), "group_id=%s", [gid], days)
    finally:
        conn.close()

    assert len(rows) == 5, "в ответе должен быть каждый день периода"
    by_date = {r["date"]: r for r in rows}
    assert by_date[today.strftime("%Y-%m-%d")]["posts"] == 2
    assert by_date[yesterday.strftime("%Y-%m-%d")]["posts"] == 1
    empty = [r for r in rows if r["date"] not in
             (today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d"))]
    assert all(r["posts"] == 0 and r["views"] == 0 for r in empty), \
        "день без постов обязан прийти нулём, а не пропасть из ряда"


def test_timeline_endpoint_still_answers(client, group_with_post):
    """Договор с интерфейсом не менялся: те же поля в том же формате."""
    gid = group_with_post["group_id"]
    r = client.get(
        f"/api/groups/{gid}/analytics/timeline?period=week",
        headers=auth(group_with_post["token"]),
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 7
    assert set(rows[0]) == {"date", "label", "views", "reactions", "posts"}


def test_db_session_uses_app_timezone():
    """
    День в аналитике режется выражением `published_at::date`, а оно считается
    в зоне сессии. Без явной установки Postgres берёт зону сервера (на Railway
    это UTC), и «сегодня» на графике заканчивалось бы в 17:00 по Красноярску.
    """
    import utils

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SHOW timezone")
        tz = c.fetchone()["TimeZone"]
    finally:
        conn.close()
    assert tz == utils.APP_TZ


# ── 2. Поиск: индекс и экранирование ────────────────────────────────────────

def test_like_pattern_escapes_wildcards():
    """
    Спецсимволы LIKE в пользовательском вводе — это данные, а не синтаксис.
    Иначе поиск «50%» означал «50 и что угодно», а «%» — «вообще всё».
    """
    assert like_pattern("50%") == "%50\\%%"
    assert like_pattern("a_b") == "%a\\_b%"
    assert like_pattern("c:\\path") == "%c:\\\\path%"


def test_search_treats_percent_as_text(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    marker = uuid.uuid4().hex[:6]
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": f"Скидка 50% {marker}", "content": "текст"},
        headers=auth(token),
    )
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": f"Без скидки {marker}", "content": "текст"},
        headers=auth(token),
    )

    found = client.get(
        f"/api/groups/{gid}/posts?q=50%25", headers=auth(token)
    ).json()["posts"]
    titles = [p["title"] for p in found]
    assert any("50%" in t for t in titles)
    assert not any("Без скидки" in t for t in titles), \
        "«%» из запроса не должен работать подстановочным знаком"


def test_search_is_case_insensitive(client, group_with_post):
    """ILIKE вместо LOWER(...) LIKE LOWER(...) — регистр по-прежнему не важен."""
    gid, token = group_with_post["group_id"], group_with_post["token"]
    marker = uuid.uuid4().hex[:6]
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": f"ФЕСТИВАЛЬ {marker}", "content": "текст"},
        headers=auth(token),
    )
    found = client.get(
        f"/api/groups/{gid}/posts?q=фестиваль%20{marker}", headers=auth(token)
    ).json()["posts"]
    assert len(found) == 1, "поиск обязан находить независимо от регистра"


def test_search_columns_are_indexed():
    """
    Индекс — весь смысл перехода на ILIKE. Если pg_trgm в окружении нет,
    миграция его сознательно пропускает (см. a9d4f1c60b72), и тогда проверять
    нечего — но молча это пройти не должно.
    """
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM pg_extension WHERE extname='pg_trgm'")
        if not c.fetchone():
            pytest.skip("pg_trgm недоступно в этом окружении — индексы пропущены")
        c.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename IN ('posts','volunteer_media') AND indexname LIKE '%%_trgm'"
        )
        names = {r["indexname"] for r in c.fetchall()}
    finally:
        conn.close()
    assert names >= {
        "ix_posts_title_trgm", "ix_posts_content_trgm", "ix_volunteer_media_event_trgm"
    }, f"нет триграммных индексов под поиск: {names}"


# ── 3. Вовлечённость: ноль просмотров — это «нет данных» ────────────────────

def test_engagement_is_none_without_views():
    """
    Раньше знаменатель страховали через max(views, 1): ноль просмотров и три
    реакции превращались в 300 %, а ноль и ноль — в «0,0 %», неотличимые от
    честного нуля.
    """
    assert _engagement(0, 3, 0) is None
    assert _engagement(None, 3, 0) is None
    assert _engagement(0, 0, 0) is None


def test_engagement_counts_when_views_are_real():
    assert _engagement(200, 10, 10) == 10.0
    assert _avg_views(300, 3) == 100
    assert _avg_views(None, 3) is None
    assert _avg_views(0, 0) is None


def test_summary_reports_no_data_instead_of_zero_percent(client, group_with_post):
    """Через API: пока статистику не собирали, показателя нет — не ноль."""
    gid, token = group_with_post["group_id"], group_with_post["token"]
    make_published(client, gid, token, app_now())
    r = client.get(f"/api/groups/{gid}/analytics/summary", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engagement_rate"] is None
    assert body["avg_views"] is None
    assert body["total_views"] == 0, "сумма просмотров остаётся числом, меняется только производное"


def test_summary_computes_engagement_once_stats_arrive(client, group_with_post):
    from stats import save_platform_stats

    gid, token = group_with_post["group_id"], group_with_post["token"]
    pid = make_published(client, gid, token, app_now())
    conn = get_db()
    try:
        save_platform_stats(conn, pid, "vk", views=1000, reactions=50, comments=50)
        conn.commit()
    finally:
        conn.close()

    body = client.get(
        f"/api/groups/{gid}/analytics/summary", headers=auth(token)
    ).json()
    assert body["engagement_rate"] == 10.0
    assert body["avg_views"] == 1000
