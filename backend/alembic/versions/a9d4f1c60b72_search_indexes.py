"""Триграммные индексы под поиск по постам

Поиск по постам — это `title ILIKE '%слово%' OR content ILIKE '%слово%'`.
Обычный btree-индекс такому шаблону не помогает вообще: подстрока может начаться
в любом месте, и Postgres честно перебирает все строки таблицы, вычитывая при
этом content целиком. На демо-данных это незаметно, на реальном архиве постов
каждый ввод буквы в строке поиска превращается в полный проход.

Расширение pg_trgm разбивает текст на триграммы и кладёт их в GIN-индекс —
после этого `ILIKE '%...%'` ищется по индексу. Оговорка одна: шаблон короче
трёх значащих символов триграммами не покрывается, и такой запрос всё равно
пойдёт перебором — для запросов из одной-двух букв это неизбежно.

Расширение — не гарантированная часть окружения. Если создать его нельзя
(нет прав, нет contrib-пакета), выкатку из-за индекса ронять неправильно:
поиск работает и без него, просто медленнее. Поэтому шаг обёрнут в SAVEPOINT
и при неудаче пропускается с предупреждением в логе.

Revision ID: a9d4f1c60b72
Revises: e3b7d2f81a45
"""
import logging

from alembic import op

revision = "a9d4f1c60b72"
down_revision = "e3b7d2f81a45"
branch_labels = None
depends_on = None

# Стандартный логгер, а не logs.get_logger: env.py намеренно не тянет модули
# приложения в процесс миграций (см. комментарий про fileConfig там же).
log = logging.getLogger("alembic.search_indexes")

# (индекс, таблица, колонка)
TRGM_INDEXES = [
    ("ix_posts_title_trgm", "posts", "title"),
    ("ix_posts_content_trgm", "posts", "content"),
    ("ix_volunteer_media_event_trgm", "volunteer_media", "event_name"),
]


def upgrade() -> None:
    bind = op.get_bind()
    try:
        # SAVEPOINT: если CREATE EXTENSION упадёт без него, транзакция миграции
        # окажется в состоянии aborted и следующая же команда откажется работать.
        with bind.begin_nested():
            bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception as e:
        log.warning(
            f"⚠️   pg_trgm недоступно ({e}); поиск по постам останется без индекса "
            "и будет идти перебором. Индексы можно создать позже: "
            "CREATE EXTENSION pg_trgm; затем повторить эту миграцию."
        )
        return

    for name, table, column in TRGM_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING GIN ({column} gin_trgm_ops)"
        )


def downgrade() -> None:
    for name, _table, _column in TRGM_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    # Расширение не сносим: его могло завести не это приложение.
