"""Все «человеческие» даты — в зоне приложения

Даты-строки «YYYY-MM-DDTHH:MM» писали два разных источника в двух разных зонах:
scheduled_at приходит из браузера по местному времени (Красноярск, UTC+7), а
created_at/joined_at/connected_at ставила база и код контейнера — в UTC. В одной
таблице лежали значения, различающиеся на семь часов, и сравнивать их между
собой было нельзя: аналитика за «сегодня» смотрела не на те сутки, а пользователь
видел время создания поста на семь часов раньше реального.

Здесь: разовый сдвиг уже накопленных значений из UTC в APP_TIMEZONE и смена
server_default, чтобы новые строки писались сразу правильно.

Что НЕ трогаем:
  * posts.scheduled_at — он и так местный, пришёл из браузера;
  * posts.published_at — сдвигаем, но только старые значения (см. PUBLISHED_CUTOFF);
  * invite_links.expires_at, password_resets/email_verifications.expires_at —
    это внутренние пары «записали utcnow / сравнили с utcnow», они согласованы
    сами с собой, и сдвиг их сломает.

Revision ID: e5c9d4a71b38
Revises: d3a8b1f60c27
"""
from alembic import op

revision = "e5c9d4a71b38"
down_revision = "d3a8b1f60c27"
branch_labels = None
depends_on = None

# Зона зашита намеренно: миграция обязана быть воспроизводимой и не зависеть от
# того, что стояло в окружении в момент запуска. Должна совпадать с APP_TZ —
# расхождение ловит check_time_alignment() при старте приложения.
APP_TIMEZONE = "Asia/Krasnoyarsk"

# Колонки, которые база заполняет сама.
DEFAULTED = [
    ("posts", "created_at"),
    ("users", "created_at"),
    ("groups", "created_at"),
    ("group_members", "joined_at"),
    ("notifications", "created_at"),
    ("volunteer_media", "created_at"),
    ("vk_settings", "connected_at"),
    ("tg_settings", "connected_at"),
    ("invite_links", "created_at"),
]

# Колонки, которые заполнял код, но тоже временем контейнера (то есть UTC).
APP_WRITTEN = [
    ("posts", "published_at"),
    ("posts", "vk_stats_updated_at"),
]

# Ровно формат, в котором даты лежат: без него сдвинули бы что-нибудь чужое.
SHAPE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"

# published_at начал писаться в зоне приложения раньше этой миграции (вместе с
# планировщиком). Значения свежее этой отметки уже местные — их сдвигать нельзя.
PUBLISHED_CUTOFF = "2026-08-15T18:00"


def _shift(table: str, column: str, direction: str, extra: str = "") -> str:
    """UTC → зона приложения (или обратно) для текстовой даты."""
    src, dst = ("UTC", APP_TIMEZONE) if direction == "to_app" else (APP_TIMEZONE, "UTC")
    return (
        f"UPDATE {table} SET {column} = to_char("  # noqa: S608 — имена свои, не из ввода
        f"  (({column}::timestamp AT TIME ZONE '{src}') AT TIME ZONE '{dst}'), "
        f"  'YYYY-MM-DD\"T\"HH24:MI') "
        f"WHERE {column} IS NOT NULL AND {column} ~ '{SHAPE}'{extra}"
    )


def _default(table: str, column: str, timezone: str | None) -> str:
    if timezone is None:
        expr = "to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"
    else:
        expr = f"to_char(CURRENT_TIMESTAMP AT TIME ZONE '{timezone}', 'YYYY-MM-DD\"T\"HH24:MI')"
    return f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {expr}"


def upgrade() -> None:
    for table, column in DEFAULTED:
        op.execute(_shift(table, column, "to_app"))
        op.execute(_default(table, column, APP_TIMEZONE))

    op.execute(_shift("posts", "vk_stats_updated_at", "to_app"))
    op.execute(
        _shift("posts", "published_at", "to_app", extra=f" AND published_at < '{PUBLISHED_CUTOFF}'")
    )


def downgrade() -> None:
    for table, column in DEFAULTED:
        op.execute(_default(table, column, None))
        op.execute(_shift(table, column, "to_utc"))
    for table, column in APP_WRITTEN:
        op.execute(_shift(table, column, "to_utc"))
