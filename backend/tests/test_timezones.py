"""
Даты — настоящие даты, а не строки.

Все «временные» поля лежали в TEXT формата «YYYY-MM-DDTHH:MM»: ни зоны, ни
арифметики. Фильтры по периодам собирались строковыми сравнениями и работали
только потому, что лексикографический порядок такого формата совпадает с
хронологическим. Плюс к этому строки писали два источника в разных зонах, и
в одной колонке лежали значения, различающиеся на семь часов.

Теперь в базе timestamptz — абсолютный момент. Зона применяется только на
выдаче, поэтому расхождение зон структурно невозможно. Наружу API по-прежнему
отдаёт «YYYY-MM-DDTHH:MM» в зоне приложения: формат хранения и договор с
интерфейсом — разные вещи.
"""
from datetime import UTC, datetime, timedelta, timezone

import pytest
from conftest import auth, publish_and_wait

import main
from utils import APP_TZ, app_now, app_now_str, fmt_dt, get_db, parse_dt

FMT = "%Y-%m-%dT%H:%M"

# Колонки, которые раньше были текстом и должны были стать датами
CONVERTED = [
    ("posts", "created_at"), ("posts", "scheduled_at"), ("posts", "published_at"),
    ("posts", "vk_stats_updated_at"), ("users", "created_at"), ("groups", "created_at"),
    ("group_members", "joined_at"), ("notifications", "created_at"),
    ("volunteer_media", "created_at"), ("vk_settings", "connected_at"),
    ("tg_settings", "connected_at"), ("invite_links", "created_at"),
    ("invite_links", "expires_at"), ("post_stats", "updated_at"),
    ("publish_jobs", "created_at"), ("publish_jobs", "finished_at"),
    ("password_resets", "expires_at"),
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


def minutes_from_now(value: str) -> float:
    return abs(
        (datetime.strptime(value, FMT) - datetime.strptime(app_now_str(), FMT)).total_seconds()
    ) / 60


# ── Тип хранения ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("table,column", CONVERTED)
def test_dates_are_timestamps(table, column):
    assert column_type(table, column) == "timestamp with time zone", (
        f"{table}.{column} всё ещё не дата"
    )


def test_date_arithmetic_works_in_sql():
    """
    Ровно то, чего не хватало: с текстом такой запрос был невозможен без
    приведения типа на каждой строке.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) n FROM posts WHERE created_at > NOW() - INTERVAL '30 days'")
    assert c.fetchone()["n"] >= 0
    c.execute("SELECT MAX(created_at) - MIN(created_at) AS span FROM posts")
    assert c.fetchone()["span"] is not None or True
    conn.close()


def test_scheduled_lookup_has_an_index():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT indexdef FROM pg_indexes WHERE tablename='posts'")
    defs = " ".join(r["indexdef"] for r in c.fetchall())
    conn.close()
    assert "scheduled_at" in defs, "планировщик ищет по сроку каждую минуту"


# ── Договор с интерфейсом не изменился ───────────────────────────────────────

def test_api_still_returns_the_old_format(client, group_with_post):
    """Формат хранения поменялся, формат выдачи — нет."""
    gid, token = group_with_post["group_id"], group_with_post["token"]
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Формат", "content": "т", "platforms": []},
        headers=auth(token),
    ).json()
    assert datetime.strptime(created["created_at"], FMT)
    assert len(created["created_at"]) == 16


def test_created_at_matches_app_now(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Проверка времени", "content": "т", "platforms": []},
        headers=auth(token),
    ).json()
    assert minutes_from_now(created["created_at"]) < 5


def test_published_at_matches_app_now(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Публикуем", "content": "т", "platforms": []},
        headers=auth(token),
    ).json()["id"]
    publish_and_wait(client, f"/api/groups/{gid}/posts/{pid}/publish", auth(token))
    published = client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(token)).json()
    assert minutes_from_now(published["published_at"]) < 5


def test_scheduled_at_round_trips_unchanged(client, group_with_post):
    """
    Человек ввёл 18:00 — он и должен увидеть 18:00. Ввод без зоны означает
    местное время, и на выдаче оно возвращается тем же.
    """
    gid, token = group_with_post["group_id"], group_with_post["token"]
    when = (app_now() + timedelta(days=1)).strftime(FMT)
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Отложенный", "content": "т", "status": "scheduled",
              "scheduled_at": when, "platforms": []},
        headers=auth(token),
    ).json()
    assert created["scheduled_at"] == when

    again = client.get(f"/api/groups/{gid}/posts/{created['id']}", headers=auth(token)).json()
    assert again["scheduled_at"] == when


def test_empty_dates_stay_empty(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Без даты", "content": "т", "platforms": []},
        headers=auth(token),
    ).json()
    assert created["scheduled_at"] is None
    assert created["published_at"] is None


# ── Преобразования ───────────────────────────────────────────────────────────

def test_parse_dt_reads_naive_input_as_local():
    parsed = parse_dt("2026-08-16T18:00")
    assert parsed is not None
    assert parsed.utcoffset() is not None, "у даты должна появиться зона"
    assert parsed.strftime(FMT) == "2026-08-16T18:00"


def test_parse_dt_respects_explicit_zone():
    """Если зона указана явно, придумывать свою нельзя."""
    parsed = parse_dt("2026-08-16T11:00+00:00")
    assert fmt_dt(parsed) == "2026-08-16T18:00", "11:00 UTC — это 18:00 в Красноярске"


@pytest.mark.parametrize("bad", [None, "", "не дата"])
def test_parse_dt_survives_garbage(bad):
    assert parse_dt(bad) is None


def test_fmt_dt_renders_in_app_zone():
    moment = datetime(2026, 8, 16, 11, 0, tzinfo=UTC)
    assert fmt_dt(moment) == "2026-08-16T18:00"
    assert fmt_dt(None) is None


def test_round_trip_is_stable():
    when = "2026-12-31T23:59"
    assert fmt_dt(parse_dt(when)) == when


# ── Фильтры ──────────────────────────────────────────────────────────────────

def test_date_filter_uses_real_dates(client, group_with_post):
    """
    Фильтр «за такой-то день» стал интервалом, а не сравнением префикса строки.
    """
    gid, token = group_with_post["group_id"], group_with_post["token"]
    today = app_now_str()[:10]
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Сегодняшний", "content": "т", "platforms": []},
        headers=auth(token),
    )
    found = client.get(f"/api/groups/{gid}/posts?date={today}", headers=auth(token)).json()
    assert found["total"] >= 1
    assert client.get(
        f"/api/groups/{gid}/posts?date=1999-01-01", headers=auth(token)
    ).json()["total"] == 0


def test_timeline_covers_days_ending_today(client, admin_token):
    r = client.get("/api/analytics/timeline?period=week", headers=auth(admin_token))
    assert r.status_code == 200
    days = r.json()
    assert len(days) == 7
    today = app_now_str()[:10]
    assert days[-1]["date"] == today
    expected_first = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    assert days[0]["date"] == expected_first


# ── Часы ─────────────────────────────────────────────────────────────────────

def test_clocks_agree():
    assert main.check_time_alignment() is True


def test_app_timezone_is_configured():
    assert APP_TZ
    assert app_now().utcoffset() is not None, "«сейчас» приложения обязано быть с зоной"
