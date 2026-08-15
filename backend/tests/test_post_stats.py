"""
Статистика хранится отдельно по каждой площадке.

Раньше posts.views и соседи были одним набором на пост, общим для ВК и
Telegram. Заполняла их только синхронизация ВК и заполняла целиком — так что
появись второй источник, площадки начали бы затирать цифры друг друга, и понять,
чьи числа сейчас в колонке, стало бы невозможно.
"""
from conftest import auth, drain_publish_queue

from stats import save_platform_stats, stats_for_posts
from utils import get_db


def published_post(client, group, title="Со статистикой"):
    gid = group["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": title, "content": "т", "platforms": ["vk", "telegram"]},
        headers=auth(group["token"]),
    ).json()["id"]
    client.post(f"/api/groups/{gid}/posts/{pid}/publish", headers=auth(group["token"]))
    drain_publish_queue()
    return pid


# ── Хранилище ────────────────────────────────────────────────────────────────

def test_platforms_do_not_overwrite_each_other(client, group_with_post):
    """Главное свойство: цифры одной площадки не трогают другую."""
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=100, reactions=10)
    save_platform_stats(conn, pid, "telegram", views=7, reactions=1)
    conn.commit()

    got = {r["platform"]: r for r in stats_for_posts(conn, [pid])[pid]}
    conn.close()

    assert got["vk"]["views"] == 100
    assert got["telegram"]["views"] == 7, "запись Telegram не должна затирать ВК и наоборот"


def test_repeated_sync_updates_only_its_platform(client, group_with_post):
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=100)
    save_platform_stats(conn, pid, "telegram", views=7)
    save_platform_stats(conn, pid, "vk", views=250)  # повторная синхронизация ВК
    conn.commit()
    got = {r["platform"]: r for r in stats_for_posts(conn, [pid])[pid]}
    conn.close()
    assert got["vk"]["views"] == 250
    assert got["telegram"]["views"] == 7


def test_missing_counter_does_not_erase_previous(client, group_with_post):
    """
    None означает «не смогли получить», а не «стало пусто». Затирать им ранее
    собранное значение нельзя — иначе неудачный запрос обнулял бы статистику.
    """
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=100, reactions=5)
    save_platform_stats(conn, pid, "vk", views=None, reactions=8)
    conn.commit()
    row = stats_for_posts(conn, [pid])[pid][0]
    conn.close()
    assert row["views"] == 100
    assert row["reactions"] == 8


def test_zero_is_kept_as_a_measurement(client, group_with_post):
    """Ноль — это результат измерения, его записать надо."""
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=0)
    conn.commit()
    row = stats_for_posts(conn, [pid])[pid][0]
    conn.close()
    assert row["views"] == 0, "ноль отличается от «не собирали»"


def test_stats_disappear_with_the_post(client, group_with_post):
    """Статистика не должна переживать пост — иначе она прицепится к чужому id."""
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=42)
    conn.commit()
    conn.close()

    gid = group_with_post["group_id"]
    assert client.delete(
        f"/api/groups/{gid}/posts/{pid}", headers=auth(group_with_post["token"])
    ).status_code == 200

    conn = get_db()
    assert stats_for_posts(conn, [pid]) == {}
    conn.close()


# ── Как это видно снаружи ────────────────────────────────────────────────────

def test_post_exposes_breakdown_and_total(client, group_with_post):
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=100, reactions=10)
    save_platform_stats(conn, pid, "telegram", views=7, reactions=1)
    conn.commit()
    conn.close()

    gid = group_with_post["group_id"]
    post = client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(group_with_post["token"])).json()

    assert post["views"] == 107, "в карточке — сумма по площадкам"
    assert post["reactions"] == 11
    by_platform = {s["platform"]: s for s in post["stats"]}
    assert by_platform["vk"]["views"] == 100
    assert by_platform["telegram"]["views"] == 7


def test_post_without_stats_shows_zeros_not_garbage(client, group_with_post):
    pid = published_post(client, group_with_post, "Без статистики")
    gid = group_with_post["group_id"]
    post = client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(group_with_post["token"])).json()
    assert post["views"] == 0
    assert post["stats"] == []


def test_publishing_does_not_reset_collected_stats(client, group_with_post):
    """
    Публикация раньше обнуляла общие счётчики. Повторная публикация не должна
    стирать уже собранное.
    """
    pid = published_post(client, group_with_post)
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=500)
    conn.commit()
    conn.close()

    gid = group_with_post["group_id"]
    client.post(f"/api/groups/{gid}/posts/{pid}/publish", headers=auth(group_with_post["token"]))
    drain_publish_queue()
    post = client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(group_with_post["token"])).json()
    assert post["views"] == 500


# ── Аналитика ────────────────────────────────────────────────────────────────

def test_platform_availability_follows_the_data(client, group_with_post, admin_token):
    """
    Признак «есть статистика» больше не захардкожен: появились цифры по
    площадке — признак включился, нет цифр — по-прежнему «нет данных».
    """
    pid = published_post(client, group_with_post)
    token = group_with_post["token"]

    before = {p["platform"]: p for p in
              client.get("/api/analytics/summary", headers=auth(token)).json()["platform_stats"]}
    assert before["telegram"]["stats_available"] is False
    assert before["telegram"]["views"] is None

    conn = get_db()
    save_platform_stats(conn, pid, "telegram", views=7, reactions=1)
    conn.commit()
    conn.close()

    after = {p["platform"]: p for p in
             client.get("/api/analytics/summary", headers=auth(token)).json()["platform_stats"]}
    assert after["telegram"]["stats_available"] is True, "цифры появились — признак должен включиться"
    assert after["telegram"]["views"] == 7


def test_summary_totals_come_from_all_platforms(client, group_with_post):
    pid = published_post(client, group_with_post)
    token = group_with_post["token"]
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=100, reactions=10)
    save_platform_stats(conn, pid, "telegram", views=7, reactions=1)
    conn.commit()
    conn.close()

    summary = client.get("/api/analytics/summary", headers=auth(token)).json()
    assert summary["total_views"] == 107
    assert summary["total_reactions"] == 11


def test_top_posts_rank_by_combined_stats(client, group_with_post):
    token = group_with_post["token"]
    quiet = published_post(client, group_with_post, "Тихий")
    loud = published_post(client, group_with_post, "Громкий")
    conn = get_db()
    save_platform_stats(conn, quiet, "vk", views=5)
    save_platform_stats(conn, loud, "telegram", views=900)
    conn.commit()
    conn.close()

    top = client.get("/api/analytics/summary", headers=auth(token)).json()["top_posts"]
    assert top[0]["id"] == loud, "пост с большими цифрами в Telegram должен быть выше"


def test_timeline_counts_all_platforms(client, group_with_post):
    pid = published_post(client, group_with_post)
    token = group_with_post["token"]
    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=100)
    save_platform_stats(conn, pid, "telegram", views=7)
    conn.commit()
    conn.close()

    days = client.get("/api/analytics/timeline?period=week", headers=auth(token)).json()
    assert sum(d["views"] for d in days) >= 107


def test_export_still_builds_with_split_stats(client, admin_token):
    r = client.get(
        "/api/analytics/export?start_date=2024-01-01&end_date=2030-01-31", headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
