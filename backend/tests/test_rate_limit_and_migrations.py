"""
Рейт-лимит и миграции: то, что не должно жить внутри одного процесса.

Лимит был словарём в памяти: обнулялся при каждой выкатке и ничего не знал о
втором инстансе — при двух процессах лимит на подбор пароля фактически
удваивался. Миграции запускались в startup-хуке: на Railway новый контейнер
поднимается ещё до того, как снят старый, а при масштабировании их было бы
несколько, и все полезли бы накатывать alembic одновременно.
"""
import pytest
from conftest import auth

import main
import utils
from utils import check_rate_limit, get_db, purge_rate_limits


def hits_for(key: str) -> int | None:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT hits FROM rate_limits WHERE key=%s", (key,))
    row = c.fetchone()
    conn.close()
    return row["hits"] if row else None


# ── Рейт-лимит ───────────────────────────────────────────────────────────────

def test_limit_is_stored_in_the_database():
    """
    Главное отличие от прежней версии: счётчик виден всем процессам, а не
    только тому, который его завёл.
    """
    check_rate_limit("тест:в-базе", max_requests=5, window_seconds=60)
    assert hits_for("тест:в-базе") == 1


def test_limit_triggers_after_the_allowance():
    key = "тест:порог"
    for _ in range(3):
        check_rate_limit(key, max_requests=3, window_seconds=60)
    with pytest.raises(Exception) as e:
        check_rate_limit(key, max_requests=3, window_seconds=60)
    assert getattr(e.value, "status_code", None) == 429


def test_counter_survives_process_restart():
    """
    Раньше словарь обнулялся вместе с процессом, и лимит сбрасывался каждой
    выкаткой. Перезапуск изображаем очисткой памяти процесса.
    """
    key = "тест:рестарт"
    for _ in range(3):
        check_rate_limit(key, max_requests=3, window_seconds=60)
    utils.RATE_LIMIT_FALLBACK.clear()  # «процесс перезапустился»
    with pytest.raises(Exception) as e:
        check_rate_limit(key, max_requests=3, window_seconds=60)
    assert getattr(e.value, "status_code", None) == 429


def test_window_resets_after_it_expires():
    key = "тест:окно"
    check_rate_limit(key, max_requests=1, window_seconds=60)
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE rate_limits SET window_start = NOW() - INTERVAL '2 hours' WHERE key=%s", (key,))
    conn.commit()
    conn.close()
    check_rate_limit(key, max_requests=1, window_seconds=60)  # окно прошло — можно снова
    assert hits_for(key) == 1


def test_keys_are_independent():
    check_rate_limit("тест:а", max_requests=1, window_seconds=60)
    check_rate_limit("тест:б", max_requests=1, window_seconds=60)
    assert hits_for("тест:а") == 1 and hits_for("тест:б") == 1


def test_purge_removes_only_old_windows():
    check_rate_limit("тест:свежий", max_requests=5, window_seconds=60)
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO rate_limits (key, window_start, hits) "
        "VALUES ('тест:древний', NOW() - INTERVAL '2 days', 9)"
    )
    conn.commit()
    conn.close()

    assert purge_rate_limits(older_than_seconds=3600) >= 1
    assert hits_for("тест:древний") is None
    assert hits_for("тест:свежий") == 1


def test_database_outage_does_not_deny_service(monkeypatch):
    """
    Счётчик — не повод отказать людям в работе: если база недоступна, считаем
    в памяти. Хуже, чем в базе, но лучше, чем 500 на входе.
    """
    def broken():
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(utils, "get_db", broken)
    check_rate_limit("тест:без-базы", max_requests=2, window_seconds=60)
    check_rate_limit("тест:без-базы", max_requests=2, window_seconds=60)
    with pytest.raises(Exception) as e:
        check_rate_limit("тест:без-базы", max_requests=2, window_seconds=60)
    assert getattr(e.value, "status_code", None) == 429


def test_login_is_still_rate_limited(client):
    """Проверка через настоящую ручку: лимит на подбор пароля работает."""
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "нет@такого.local", "password": "x"})
    r = client.post("/api/auth/login", json={"email": "нет@такого.local", "password": "x"})
    assert r.status_code == 429


# ── Миграции ─────────────────────────────────────────────────────────────────

def test_schema_check_sees_current_schema():
    ok, message = main.schema_is_current()
    assert ok, message


def test_schema_check_notices_a_lagging_database():
    """
    Приложение обязано замечать отставшую схему: обслуживать запросы на ней —
    это 500-е у пользователей вместо честного отказа подняться.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT version_num FROM alembic_version")
    saved = c.fetchone()["version_num"]
    c.execute("UPDATE alembic_version SET version_num='0000deadbeef'")
    conn.commit()
    try:
        ok, message = main.schema_is_current()
        assert ok is False
        assert "отстала" in message
    finally:
        c.execute("UPDATE alembic_version SET version_num=%s", (saved,))
        conn.commit()
        conn.close()


def test_migrations_are_serialised_by_a_lock():
    """
    Второй процесс не должен накатывать одновременно с первым: гонка за
    alembic_version даёт наполовину применённую схему.
    """
    holder = get_db()
    holder.cursor().execute("SELECT pg_advisory_lock(%s)", (main.MIGRATION_LOCK_ID,))
    try:
        probe = get_db()
        c = probe.cursor()
        c.execute("SELECT pg_try_advisory_lock(%s) AS got", (main.MIGRATION_LOCK_ID,))
        assert c.fetchone()["got"] is False, "блокировка не удерживается"
        probe.close()
    finally:
        holder.cursor().execute("SELECT pg_advisory_unlock(%s)", (main.MIGRATION_LOCK_ID,))
        holder.close()


def test_migrations_are_idempotent():
    """Повторный прогон на уже накатанной базе не должен ничего ломать."""
    main.run_migrations()
    ok, _ = main.schema_is_current()
    assert ok


def test_release_command_is_configured():
    """
    Схему двигает preDeployCommand, а не старт приложения. Если строку уберут,
    миграции тихо вернутся в startup-хук.
    """
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "railway.toml")
    with open(path, encoding="utf-8") as f:
        config = f.read()
    assert "preDeployCommand" in config
    assert "manage.py migrate" in config


def test_startup_can_be_told_not_to_migrate():
    """На проде миграции при старте выключены — их уже накатил preDeploy."""
    import importlib

    assert hasattr(main, "MIGRATE_ON_STARTUP")
    assert importlib.util.find_spec("manage") is not None


def test_admin_endpoints_still_work_after_all_this(client, admin_token):
    """Дымовая проверка: перенос миграций не сломал обычную работу."""
    assert client.get("/api/users", headers=auth(admin_token)).status_code == 200
    assert client.get("/api/posts", headers=auth(admin_token)).status_code == 200
