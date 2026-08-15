"""
Все «человеческие» даты живут в одной зоне.

Даты-строки «YYYY-MM-DDTHH:MM» писали два источника в двух зонах: scheduled_at
приходит из браузера по местному времени (Красноярск, UTC+7), а created_at и
прочие ставила база и код контейнера — в UTC. В одной колонке лежали значения,
различающиеся на семь часов: аналитика за «сегодня» смотрела не на те сутки, а
время создания поста показывалось на семь часов раньше реального.
"""
import importlib.util
import os
from datetime import datetime, timedelta

import pytest
from conftest import auth

import main
from utils import APP_TZ, app_now_str, get_db


def _load_migration():
    """
    Миграцию грузим по пути: каталог alembic/versions не пакет, а имя `alembic`
    занято самой библиотекой.
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic", "versions", "e5c9d4a71b38_dates_to_app_timezone.py",
    )
    spec = importlib.util.spec_from_file_location("tz_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()
APP_TIMEZONE = migration.APP_TIMEZONE
DEFAULTED = migration.DEFAULTED
_shift = migration._shift

FMT = "%Y-%m-%dT%H:%M"


def minutes_from_now(value: str) -> float:
    return abs((datetime.strptime(value, FMT) - datetime.strptime(app_now_str(), FMT)).total_seconds()) / 60


# ── Что пишет база ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("table,column", DEFAULTED)
def test_defaults_use_app_timezone(table, column):
    """Дефолт каждой такой колонки обязан считать время в зоне приложения."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    default = (c.fetchone() or {}).get("column_default") or ""
    conn.close()
    assert APP_TIMEZONE in default, f"{table}.{column} пишется не в зоне приложения: {default}"


def test_migration_timezone_matches_app_setting():
    """
    Зона в миграции зашита, зона приложения — в переменной. Разъедутся —
    вернётся ровно та же беда с двумя часовыми поясами в одной колонке.
    """
    assert APP_TIMEZONE == APP_TZ


def test_created_at_matches_app_now(client, group_with_post):
    """Свежесозданный пост должен иметь время создания «сейчас», а не ±7 часов."""
    gid = group_with_post["group_id"]
    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Проверка времени", "content": "т", "platforms": []},
        headers=auth(group_with_post["token"]),
    ).json()
    assert minutes_from_now(created["created_at"]) < 5, (
        f"created_at={created['created_at']}, а сейчас {app_now_str()}"
    )


def test_published_at_matches_app_now(client, group_with_post):
    gid = group_with_post["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Публикуем", "content": "т", "platforms": []},
        headers=auth(group_with_post["token"]),
    ).json()["id"]
    published = client.post(
        f"/api/groups/{gid}/posts/{pid}/publish", headers=auth(group_with_post["token"])
    ).json()
    assert minutes_from_now(published["published_at"]) < 5


def test_user_created_at_matches_app_now(client, make_user):
    """Регистрация идёт другим путём — время всё равно должно быть местным."""
    token, uid = make_user("tz")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT created_at FROM users WHERE id=%s", (uid,))
    created_at = c.fetchone()["created_at"]
    conn.close()
    assert minutes_from_now(created_at) < 5


# ── Сам сдвиг ────────────────────────────────────────────────────────────────

def test_shift_moves_utc_value_into_app_timezone():
    """
    Разовый перенос накопленных значений. Проверяем на отдельной таблице тем же
    выражением, что и в миграции: на боевых данных это делалось один раз.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS tz_probe")
    c.execute("CREATE TABLE tz_probe (created_at TEXT)")
    c.execute("INSERT INTO tz_probe (created_at) VALUES ('2026-05-30T22:05')")
    c.execute(_shift("tz_probe", "created_at", "to_app"))
    c.execute("SELECT created_at FROM tz_probe")
    shifted = c.fetchone()["created_at"]
    conn.commit()

    assert shifted == "2026-05-31T05:05", "Красноярск на 7 часов впереди Гринвича"

    # И обратно — downgrade должен возвращать ровно исходное значение
    c.execute(_shift("tz_probe", "created_at", "to_utc"))
    c.execute("SELECT created_at FROM tz_probe")
    assert c.fetchone()["created_at"] == "2026-05-30T22:05"
    c.execute("DROP TABLE tz_probe")
    conn.commit()
    conn.close()


def test_shift_leaves_foreign_formats_alone():
    """
    Сдвиг не должен трогать значения другого вида: invite_links.expires_at
    лежит в ISO с «Z» и сравнивается с utcnow — тронешь, и приглашения сломаются.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS tz_probe2")
    c.execute("CREATE TABLE tz_probe2 (created_at TEXT)")
    c.execute("INSERT INTO tz_probe2 (created_at) VALUES ('2026-05-31T04:07:56.502953Z'), (NULL)")
    c.execute(_shift("tz_probe2", "created_at", "to_app"))
    c.execute("SELECT created_at FROM tz_probe2 WHERE created_at IS NOT NULL")
    assert c.fetchone()["created_at"] == "2026-05-31T04:07:56.502953Z"
    c.execute("DROP TABLE tz_probe2")
    conn.commit()
    conn.close()


def test_scheduled_at_is_not_in_the_shift_list():
    """
    scheduled_at приходит из браузера уже местным. Сдвинуть его — значит увести
    все отложенные посты на семь часов.
    """
    assert ("posts", "scheduled_at") not in DEFAULTED + migration.APP_WRITTEN


# ── Предохранитель ───────────────────────────────────────────────────────────

def test_alignment_check_passes_when_zones_agree():
    assert main.check_time_alignment() is True


def test_alignment_check_notices_divergence(monkeypatch, capsys):
    """Расхождение зон должно быть видно в логе, а не всплыть месяцем позже."""
    import utils

    monkeypatch.setattr(utils, "APP_TZ", "UTC")
    assert main.check_time_alignment() is False
    assert "расходятся во времени" in capsys.readouterr().out


def test_alignment_check_does_not_crash_startup(monkeypatch):
    """Перекос времени — повод предупредить, но не отказывать людям в работе."""
    import utils

    monkeypatch.setattr(utils, "APP_TZ", "UTC")
    main.check_time_alignment()  # не должно бросить


# ── Аналитика ────────────────────────────────────────────────────────────────

def test_timeline_covers_days_ending_today(client, admin_token):
    """
    Окна периодов строятся от «сейчас» приложения. Считай их по UTC — и
    сегодняшний день выпал бы из выборки на семь часов в сутки.
    """
    r = client.get("/api/analytics/timeline?period=week", headers=auth(admin_token))
    assert r.status_code == 200
    days = r.json()
    assert len(days) == 7
    today = app_now_str()[:10]
    assert days[-1]["date"] == today, f"последний день таймлайна {days[-1]['date']}, а сегодня {today}"
    expected_first = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    assert days[0]["date"] == expected_first
