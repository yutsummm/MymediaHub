"""
Схема живёт только в alembic. Эти тесты ловят два способа сломать это:
DDL, просочившийся обратно в код приложения, и миграцию, которая не накатывается
на базу, созданную до перехода на alembic.
"""
import os
import re
import tokenize

import psycopg2
import psycopg2.extras
import pytest
from conftest import TEST_DATABASE_URL, _server_url

import main

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXPECTED_TABLES = {
    "users", "posts", "templates", "notifications", "vk_settings", "tg_settings",
    "email_verifications", "password_resets", "groups", "group_members",
    "invite_links", "volunteer_media",
}


def test_migrations_created_all_tables(db):
    c = db.cursor()
    c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = {r["table_name"] for r in c.fetchall()}
    assert tables >= EXPECTED_TABLES


def test_alembic_version_is_recorded(db):
    c = db.cursor()
    c.execute("SELECT version_num FROM alembic_version")
    assert c.fetchone()["version_num"]


def _strip_comments(path: str) -> str:
    """Исходник без комментариев — чтобы тест не срабатывал на упоминание DDL в пояснении."""
    with open(path, "rb") as fh:
        tokens = tokenize.tokenize(fh.readline)
        return "".join(
            tok.string for tok in tokens if tok.type not in (tokenize.COMMENT, tokenize.NL)
        )


def test_app_code_contains_no_ddl():
    """CREATE TABLE / ALTER TABLE в коде приложения — признак вернувшегося init_db()."""
    offenders = []
    for root, dirs, files in os.walk(BACKEND_DIR):
        dirs[:] = [
            d for d in dirs
            if d not in {"alembic", "tests", "__pycache__", "uploads"} and not d.startswith(".")
        ]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            if re.search(r"\b(CREATE TABLE|ALTER TABLE)\b", _strip_comments(path), re.IGNORECASE):
                offenders.append(os.path.relpath(path, BACKEND_DIR))
    assert not offenders, f"DDL должен жить в миграциях alembic, а не в {offenders}"


def test_seed_is_idempotent(client, db):
    c = db.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    before = c.fetchone()["count"]
    main.seed_db()
    c.execute("SELECT COUNT(*) FROM users")
    assert c.fetchone()["count"] == before


def test_migrations_are_idempotent(database):
    """Повторный upgrade head ничего не ломает — как при рестарте контейнера."""
    main.run_migrations()
    main.run_migrations()


def test_database_url_with_percent_is_not_mangled(database):
    """
    Railway отдаёт URL-encoded пароль (%40 вместо @). Если URL пойдёт через
    alembic.ini, ConfigParser либо упадёт на интерполяции, либо съест «%».
    """
    from alembic.config import Config

    tricky = "postgresql://user:p%40ss%2Fword@host:5432/railway"
    original = main.DATABASE_URL
    main.DATABASE_URL = tricky
    try:
        cfg = main._alembic_config()
    finally:
        main.DATABASE_URL = original

    assert cfg.attributes["db_url"] == tricky
    # URL не должен попадать в ini-секцию, где его тронет интерполяция
    assert not cfg.get_main_option("sqlalchemy.url", None)
    assert isinstance(cfg, Config)


def test_incomplete_legacy_database_is_rejected(legacy_database):
    """
    Неполную «дореформенную» базу нельзя молча пометить baseline-ревизией:
    штамп сказал бы, что схема актуальна, а колонки бы не хватало.
    """
    conn = psycopg2.connect(legacy_database)
    conn.autocommit = True
    conn.cursor().execute("ALTER TABLE posts DROP COLUMN vk_stats_updated_at")
    conn.close()

    import utils
    original_utils, original_main = utils.DATABASE_URL, main.DATABASE_URL
    utils.DATABASE_URL = main.DATABASE_URL = legacy_database
    try:
        with pytest.raises(RuntimeError, match="vk_stats_updated_at"):
            main.run_migrations()
    finally:
        utils.DATABASE_URL, main.DATABASE_URL = original_utils, original_main


@pytest.fixture()
def legacy_database():
    """База с таблицами, но без alembic_version — как прод до перехода на alembic."""
    server_url, dbname = _server_url(TEST_DATABASE_URL)
    legacy_name = f"{dbname}_legacy"
    legacy_url = f"{server_url.rsplit('/', 1)[0]}/{legacy_name}"

    admin = psycopg2.connect(server_url)
    admin.autocommit = True
    ac = admin.cursor()
    ac.execute(f'DROP DATABASE IF EXISTS "{legacy_name}"')
    ac.execute(f'CREATE DATABASE "{legacy_name}"')

    # Схему собираем миграциями до BASELINE_REVISION (именно её оставлял после
    # себя старый init_db()), затем стираем след alembic. Гнать до head нельзя:
    # получилась бы база новее «легаси», и последующий upgrade падал бы на
    # «колонка уже существует» — как раз то, что этот тест должен ловить.
    original = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = legacy_url
    import utils
    original_utils_url = utils.DATABASE_URL
    original_main_url = main.DATABASE_URL
    utils.DATABASE_URL = legacy_url
    main.DATABASE_URL = legacy_url
    try:
        from alembic import command

        command.upgrade(main._alembic_config(), main.BASELINE_REVISION)
        conn = psycopg2.connect(legacy_url)
        conn.autocommit = True
        conn.cursor().execute("DROP TABLE alembic_version")
        conn.close()
        yield legacy_url
    finally:
        os.environ["DATABASE_URL"] = original
        utils.DATABASE_URL = original_utils_url
        main.DATABASE_URL = original_main_url
        ac.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid <> pg_backend_pid()",
            (legacy_name,),
        )
        ac.execute(f'DROP DATABASE IF EXISTS "{legacy_name}"')
        admin.close()


def test_legacy_database_gets_stamped_not_recreated(legacy_database):
    """
    На базе без alembic_version миграции не должны падать на «таблица уже есть»:
    она помечается базовой ревизией, данные остаются на месте.
    """
    conn = psycopg2.connect(legacy_database)
    conn.autocommit = True
    conn.cursor().execute(
        "INSERT INTO users (name, email, role) VALUES ('Старый', 'legacy@test.local', 'editor')"
    )
    conn.close()

    import utils
    original_utils_url = utils.DATABASE_URL
    original_main_url = main.DATABASE_URL
    utils.DATABASE_URL = legacy_database
    main.DATABASE_URL = legacy_database
    try:
        main.run_migrations()
    finally:
        utils.DATABASE_URL = original_utils_url
        main.DATABASE_URL = original_main_url

    conn = psycopg2.connect(legacy_database, cursor_factory=psycopg2.extras.RealDictCursor)
    c = conn.cursor()
    # База помечается базовой ревизией, а затем догоняется до head обычным
    # upgrade — данные при этом остаются на месте.
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(main._alembic_config()).get_current_head()
    c.execute("SELECT version_num FROM alembic_version")
    assert c.fetchone()["version_num"] == head
    c.execute("SELECT COUNT(*) FROM users WHERE email='legacy@test.local'")
    assert c.fetchone()["count"] == 1
    # Ровно то, ради чего нужен догоняющий upgrade: поздние миграции доехали
    c.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='email_verifications' AND column_name='invite_token'"
    )
    assert c.fetchone(), "после штампа база должна догнаться до head"
    conn.close()


def test_unlimited_invite_link_is_allowed(client, admin_token):
    """max_uses = NULL должен проходить — это безлимитная ссылка."""
    from conftest import auth

    gid = client.post(
        "/api/groups", json={"name": "Безлимит", "description": ""}, headers=auth(admin_token)
    ).json()["id"]
    r = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": None},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["max_uses"] is None
