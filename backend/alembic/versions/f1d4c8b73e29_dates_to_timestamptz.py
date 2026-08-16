"""Даты становятся настоящими датами

Все «временные» поля лежали в TEXT формата «YYYY-MM-DDTHH:MM». Ни зоны, ни
арифметики: любой фильтр по периоду собирался строковыми сравнениями —
`published_at LIKE '2026-08-16%'`, `BETWEEN '...' AND '...'`. Работало это
только потому, что лексикографический порядок у такого формата совпадает с
хронологическим; шаг вправо — и всё рассыпается: ни «за последние сутки», ни
«плюс три дня», ни сравнение с now() без приведения типа.

Переводим в timestamptz. Значения в этих колонках сейчас — местное время
Красноярска (см. миграцию e5c9d4a71b38), так что интерпретируем их в APP_TIMEZONE.

Отдельно и по-другому:
  * invite_links.expires_at — ISO с «Z», это UTC;
  * password_resets/email_verifications.expires_at — уже timestamp без зоны,
    писались через utcnow.

Наружу API по-прежнему отдаёт «YYYY-MM-DDTHH:MM» в зоне приложения: формат
хранения меняется, договор с интерфейсом — нет.

Revision ID: f1d4c8b73e29
Revises: e7a2b9f41c58
"""
from alembic import op

revision = "f1d4c8b73e29"
down_revision = "e7a2b9f41c58"
branch_labels = None
depends_on = None

APP_TIMEZONE = "Asia/Krasnoyarsk"

# Колонки с местным временем в формате «YYYY-MM-DDTHH:MM»
LOCAL_TEXT_DATES = [
    ("posts", "created_at"),
    ("posts", "scheduled_at"),
    ("posts", "published_at"),
    ("posts", "vk_stats_updated_at"),
    ("users", "created_at"),
    ("groups", "created_at"),
    ("group_members", "joined_at"),
    ("notifications", "created_at"),
    ("volunteer_media", "created_at"),
    ("vk_settings", "connected_at"),
    ("tg_settings", "connected_at"),
    ("invite_links", "created_at"),
    ("post_stats", "updated_at"),
    ("publish_jobs", "created_at"),
    ("publish_jobs", "finished_at"),
]

NOW_DEFAULT = f"to_char(CURRENT_TIMESTAMP AT TIME ZONE '{APP_TIMEZONE}', 'YYYY-MM-DD\"T\"HH24:MI')"


def upgrade() -> None:
    for table, column in LOCAL_TEXT_DATES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        # Пустые строки в дате — это «не задано», а не «начало эпохи»
        op.execute(f"UPDATE {table} SET {column} = NULL WHERE btrim({column}) = ''")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE timestamptz "
            f"USING ({column}::timestamp AT TIME ZONE '{APP_TIMEZONE}')"
        )
    # Дефолты теперь ставит сама база, без форматирования в строку
    for table, column in (("posts", "created_at"), ("users", "created_at"),
                          ("groups", "created_at"), ("group_members", "joined_at"),
                          ("notifications", "created_at"), ("volunteer_media", "created_at"),
                          ("invite_links", "created_at")):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT NOW()")

    # Здесь лежит ISO с «Z» — это UTC, а не местное время
    op.execute(
        "ALTER TABLE invite_links ALTER COLUMN expires_at TYPE timestamptz "
        "USING expires_at::timestamptz"
    )
    # А эти уже timestamp, писались через utcnow
    for table in ("password_resets", "email_verifications"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN expires_at TYPE timestamptz "
            f"USING (expires_at AT TIME ZONE 'UTC')"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at TYPE timestamptz "
            f"USING (created_at AT TIME ZONE 'UTC')"
        )

    # Планировщик каждую минуту ищет по сроку — теперь это может быть индекс
    op.execute("DROP INDEX IF EXISTS ix_posts_scheduled")
    op.execute("CREATE INDEX ix_posts_scheduled ON posts (status, scheduled_at)")
    op.execute("CREATE INDEX ix_posts_published ON posts (published_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_published")
    for table in ("password_resets", "email_verifications"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at TYPE timestamp "
            f"USING (created_at AT TIME ZONE 'UTC')"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN expires_at TYPE timestamp "
            f"USING (expires_at AT TIME ZONE 'UTC')"
        )
    op.execute(
        "ALTER TABLE invite_links ALTER COLUMN expires_at TYPE TEXT "
        "USING to_char(expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')"
    )
    for table, column in LOCAL_TEXT_DATES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT "
            f"USING to_char({column} AT TIME ZONE '{APP_TIMEZONE}', 'YYYY-MM-DD\"T\"HH24:MI')"
        )
    for table, column in (("posts", "created_at"), ("users", "created_at"),
                          ("groups", "created_at"), ("group_members", "joined_at"),
                          ("notifications", "created_at"), ("volunteer_media", "created_at"),
                          ("invite_links", "created_at")):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {NOW_DEFAULT}")
