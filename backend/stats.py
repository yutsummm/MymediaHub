"""
Статистика постов по площадкам.

Раньше счётчики были одним набором на пост (posts.views и соседи), общим для
ВК и Telegram. Писала их только синхронизация ВК и писала целиком — так что
второй источник неминуемо затирал бы первый. Теперь на каждую пару
(пост, площадка) своя строка в post_stats.

NULL в счётчике означает «не собирали», ноль — «собрали, там ноль». Разница
принципиальная: именно из-за её отсутствия вконтактовские просмотры когда-то
показывались как телеграмные.
"""
from utils import app_now, row_to_dict

# Площадки, по которым вообще ведётся учёт
PLATFORMS = ("vk", "telegram")
FIELDS = ("views", "reactions", "comments", "shares")


def save_platform_stats(conn, post_id: int, platform: str, **counters) -> None:
    """
    Записывает счётчики одной площадки, не трогая остальные.

    Переданные None игнорируются: «не смогли получить просмотры» не должно
    затирать ранее собранное значение.
    """
    known = {k: v for k, v in counters.items() if k in FIELDS and v is not None}
    if not known:
        return
    columns = list(known)
    c = conn.cursor()
    c.execute(
        f"INSERT INTO post_stats (post_id, platform, {', '.join(columns)}, updated_at) "  # noqa: S608 — имена из FIELDS
        f"VALUES (%s, %s, {', '.join(['%s'] * len(columns))}, %s) "
        "ON CONFLICT (post_id, platform) DO UPDATE SET "
        + ", ".join(f"{col} = EXCLUDED.{col}" for col in columns)
        + ", updated_at = EXCLUDED.updated_at",
        [post_id, platform, *[known[col] for col in columns], app_now()],
    )


def stats_for_posts(conn, post_ids: list[int]) -> dict[int, list[dict]]:
    """Разбивка по площадкам для набора постов: {post_id: [строки post_stats]}."""
    if not post_ids:
        return {}
    c = conn.cursor()
    c.execute(
        "SELECT post_id, platform, views, reactions, comments, shares, updated_at "
        "FROM post_stats WHERE post_id = ANY(%s) ORDER BY platform",
        (list(post_ids),),
    )
    by_post: dict[int, list[dict]] = {}
    for row in c.fetchall():
        by_post.setdefault(row["post_id"], []).append(dict(row))
    return by_post


def attach_stats(conn, posts: list[dict]) -> list[dict]:
    """
    Дополняет посты статистикой: разбивкой по площадкам и суммой по ним.

    Суммы остаются числами (фронт показывает их в карточках), но складываются
    только реально собранные значения — недостающая площадка добавляет ноль,
    а не выдуманное число.
    """
    posts = [p for p in posts if p]
    by_post = stats_for_posts(conn, [p["id"] for p in posts if p.get("id") is not None])
    for post in posts:
        rows = by_post.get(post.get("id"), [])
        post["stats"] = [
            {
                "platform": r["platform"],
                **{f: r[f] for f in FIELDS},
                "updated_at": r["updated_at"],
                # Хоть что-то собрано по этой площадке
                "available": any(r[f] is not None for f in FIELDS),
            }
            for r in rows
        ]
        for field in FIELDS:
            post[field] = sum(r[field] or 0 for r in rows)
    return posts


def serialize_post(conn, row):
    """Пост наружу — со статистикой."""
    d = row_to_dict(row)
    if not d:
        return d
    return attach_stats(conn, [d])[0]


def serialize_posts(conn, rows) -> list[dict]:
    return attach_stats(conn, [row_to_dict(r) for r in rows])


# ── Агрегаты для аналитики ───────────────────────────────────────────────────

def totals_for_scope(conn, where: str, params: list) -> dict:
    """Суммы по всем площадкам для набора постов, заданного условием."""
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(SUM(s.views),0) v, COALESCE(SUM(s.reactions),0) r, "
        "       COALESCE(SUM(s.comments),0) cm, COALESCE(SUM(s.shares),0) sh "
        "FROM post_stats s JOIN posts p ON p.id = s.post_id "  # noqa: S608 — where собирается из своих кусков
        f"WHERE {where}",
        params,
    )
    row = c.fetchone()
    return {"views": row["v"], "reactions": row["r"], "comments": row["cm"], "shares": row["sh"]}


def platform_breakdown(conn, where: str, params: list) -> dict[str, dict]:
    """{площадка: {counted: сколько постов с данными, views, reactions}}."""
    c = conn.cursor()
    c.execute(
        "SELECT s.platform, COUNT(*) cnt, SUM(s.views) v, SUM(s.reactions) r "
        "FROM post_stats s JOIN posts p ON p.id = s.post_id "  # noqa: S608
        f"WHERE {where} GROUP BY s.platform",
        params,
    )
    return {
        row["platform"]: {"counted": row["cnt"], "views": row["v"], "reactions": row["r"]}
        for row in c.fetchall()
    }
