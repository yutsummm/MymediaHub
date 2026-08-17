"""
Миграции не должны полагаться на то, как называются ограничения.

Прод-база родилась не из миграций: её создавал старый `init_db()` обычными
CREATE TABLE, а при переходе на alembic её пометили BASELINE_REVISION без
повторного DDL. Значит, внешние ключи там носят имена по умолчанию от
PostgreSQL (`posts_group_id_fkey`), а не те, что даёт `op.create_foreign_key`
(`posts_group_fk`).

Миграция `e3b7d2f81a45` снимала ключи по захардкоженным именам — и выкатка
останавливалась на первом же:

    constraint "posts_group_fk" of relation "posts" does not exist

Здесь база приводится к тому же виду, что на проде (имена ключей заменяются на
умолчательные), и проверяется, что схема доезжает до head. Тест дорогой —
поднимает отдельную базу и катит всю цепочку, — но дешевле, чем узнать об этом
второй раз из упавшего деплоя.
"""
import os

import psycopg2
import pytest
from conftest import TEST_DATABASE_URL, _server_url

# Ревизия, на которой стоит прод: последняя перед правилами удаления.
BASELINE = "f1d4c8b73e29"

# (таблица, колонка, имя из миграций, имя по умолчанию от PostgreSQL)
RENAMES = [
    ("posts", "group_id", "posts_group_fk", "posts_group_id_fkey"),
    ("notifications", "group_id", "notifications_group_fk", "notifications_group_id_fkey"),
    ("vk_settings", "workspace_id", "vk_settings_workspace_fk", "vk_settings_workspace_id_fkey"),
    ("tg_settings", "workspace_id", "tg_settings_workspace_fk", "tg_settings_workspace_id_fkey"),
]


def _fk_name(cur, table: str, column: str) -> str | None:
    cur.execute(
        "SELECT c.conname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
        "WHERE c.contype='f' AND c.conrelid = to_regclass(%s) AND a.attname = %s "
        "  AND array_length(c.conkey, 1) = 1 LIMIT 1",
        (table, column),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _delete_rule(cur, table: str, column: str) -> str | None:
    cur.execute(
        "SELECT c.confdeltype FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
        "WHERE c.contype='f' AND c.conrelid = to_regclass(%s) AND a.attname = %s LIMIT 1",
        (table, column),
    )
    row = cur.fetchone()
    return row[0] if row else None


@pytest.fixture()
def legacy_db(database):
    """База в том же виде, в каком её застаёт выкатка на проде."""
    server_url, base_name = _server_url(TEST_DATABASE_URL)
    name = f"{base_name}_legacy"

    admin = psycopg2.connect(server_url)
    admin.autocommit = True
    admin.cursor().execute(f'DROP DATABASE IF EXISTS "{name}"')
    admin.cursor().execute(f'CREATE DATABASE "{name}"')
    admin.close()

    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + name
    yield url

    admin = psycopg2.connect(server_url)
    admin.autocommit = True
    admin.cursor().execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname=%s AND pid <> pg_backend_pid()",
        (name,),
    )
    admin.cursor().execute(f'DROP DATABASE IF EXISTS "{name}"')
    admin.close()


def _alembic(url: str):
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    cfg.attributes["db_url"] = url
    return command, cfg


def test_upgrade_survives_default_constraint_names(legacy_db):
    command, cfg = _alembic(legacy_db)

    # Доводим до состояния прода...
    command.upgrade(cfg, BASELINE)

    # ...и переименовываем ключи так, как их назвал бы обычный CREATE TABLE.
    conn = psycopg2.connect(legacy_db)
    conn.autocommit = True
    cur = conn.cursor()
    for table, column, made_by_alembic, postgres_default in RENAMES:
        assert _fk_name(cur, table, column) == made_by_alembic
        cur.execute(
            f'ALTER TABLE {table} RENAME CONSTRAINT "{made_by_alembic}" '
            f'TO "{postgres_default}"'
        )
    conn.close()

    # Вот на этом месте выкатка и падала.
    command.upgrade(cfg, "head")

    conn = psycopg2.connect(legacy_db)
    cur = conn.cursor()
    cur.execute("SELECT version_num FROM alembic_version")
    assert cur.fetchone() is not None, "схема должна доехать до head"

    # Правила удаления обязаны быть выставлены, а не просто «миграция прошла»:
    # c = CASCADE, n = SET NULL (pg_constraint.confdeltype).
    assert _delete_rule(cur, "posts", "group_id") == "c"
    assert _delete_rule(cur, "notifications", "group_id") == "c"
    assert _delete_rule(cur, "posts", "author_id") == "n"
    assert _delete_rule(cur, "groups", "created_by") == "n"

    # И имя приведено к каноничному, как бы ключ ни назывался до миграции.
    assert _fk_name(cur, "posts", "group_id") == "posts_group_fk"
    conn.close()
