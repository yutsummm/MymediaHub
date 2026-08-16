"""JSON-колонки становятся jsonb

platforms, tags, media и tg_message_ids лежали в TEXT: приложение само делало
json.dumps на запись и json.loads на чтение, а база видела просто строку.
Отсюда фильтры вида `platforms LIKE '%"vk"%'` — их нельзя ни проиндексировать,
ни написать без риска. Такой шаблон совпал бы и на теге «vk» внутри чужого
слова, и на подстроке в тексте, попади она в ту же колонку.

После перевода в jsonb фильтр становится `platforms ? 'vk'` — операция по
индексу GIN, а не перебор всех строк с подстрокой.

Revision ID: e7a2b9f41c58
Revises: d9e1c73b5a26
"""
from alembic import op

revision = "e7a2b9f41c58"
down_revision = "d9e1c73b5a26"
branch_labels = None
depends_on = None

# (таблица, колонка, значение по умолчанию)
COLUMNS = [
    ("posts", "platforms", "[]"),
    ("posts", "tags", "[]"),
    ("posts", "media", "[]"),
    ("posts", "tg_message_ids", "[]"),
    ("volunteer_media", "media", "[]"),
    ("templates", "fields", "[]"),
]


def upgrade() -> None:
    for table, column, default in COLUMNS:
        # Пустые строки и мусор в колонке встречаются: до сих пор её содержимое
        # ничем не проверялось. Приводим такие значения к пустому списку, иначе
        # приведение типа упало бы на первой же битой строке.
        op.execute(
            f"UPDATE {table} SET {column} = '{default}' "  # noqa: S608 — имена свои, не из ввода
            f"WHERE {column} IS NULL OR btrim({column}) = '' "
            f"   OR NOT ({column} ~ '^\\s*[\\[{{]')"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE jsonb USING {column}::jsonb"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'::jsonb")

    # Ради этого всё и делалось: фильтры по площадкам и тегам идут по индексу,
    # а не перебором строк с LIKE '%"vk"%'.
    op.execute("CREATE INDEX ix_posts_platforms ON posts USING GIN (platforms)")
    op.execute("CREATE INDEX ix_posts_tags ON posts USING GIN (tags)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_tags")
    op.execute("DROP INDEX IF EXISTS ix_posts_platforms")
    for table, column, default in COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT USING {column}::text"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
