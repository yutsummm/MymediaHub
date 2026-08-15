"""
Общие фикстуры для тестов.

Тесты идут против настоящего PostgreSQL — схема создаётся теми же миграциями,
что и на проде, поэтому SQL в роутерах проверяется по-честному. Подключение
берётся из TEST_DATABASE_URL, по умолчанию — база mediahub_test на локальном
постгресе из docker-compose. База пересоздаётся один раз за сессию.
"""
import os
import uuid

import psycopg2
import pytest

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://mediahub:mediahub123@localhost:5432/mediahub_test",
)

# utils читает DATABASE_URL на импорте, поэтому переменные ставим до импорта main.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")


def _server_url(url: str) -> tuple[str, str]:
    """Разбивает URL на (URL служебной базы postgres, имя целевой базы)."""
    base, _, dbname = url.rpartition("/")
    return f"{base}/postgres", dbname


def _recreate_database() -> None:
    server_url, dbname = _server_url(TEST_DATABASE_URL)
    conn = psycopg2.connect(server_url)
    conn.autocommit = True
    c = conn.cursor()
    c.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname=%s AND pid <> pg_backend_pid()",
        (dbname,),
    )
    c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    c.execute(f'CREATE DATABASE "{dbname}"')
    conn.close()


@pytest.fixture(scope="session", autouse=True)
def database():
    """
    Готовит чистую тестовую базу. Если PostgreSQL недоступен или у пользователя
    нет прав на CREATE DATABASE — тесты пропускаются с внятной подсказкой,
    а не падают стеной ошибок.
    """
    try:
        _recreate_database()
    except psycopg2.Error as e:
        pytest.skip(
            f"Тестовая база недоступна: {str(e).strip()}\n"
            f"URL: {TEST_DATABASE_URL}\n"
            "Поднимите PostgreSQL (docker compose up -d postgres) "
            "или задайте TEST_DATABASE_URL."
        )

    import main

    main.run_migrations()
    main.seed_db()
    yield


@pytest.fixture(scope="session")
def app(database):
    import main

    return main.app


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """
    Лимитер считает запросы по IP, а у всех тестов IP один и тот же — без сброса
    четвёртая регистрация в сессии упиралась бы в 429.
    """
    import utils

    utils.RATE_LIMIT_STORE.clear()
    yield
    utils.RATE_LIMIT_STORE.clear()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    # Без контекстного менеджера: startup-хук уже отработал в фикстуре database,
    # повторять миграции и сиды на каждом тесте незачем.
    return TestClient(app)


@pytest.fixture()
def db():
    from utils import get_db

    conn = get_db()
    yield conn
    conn.close()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def make_user(client):
    """Регистрирует нового пользователя и отдаёт (токен, id)."""

    def _make(prefix: str = "user"):
        email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.local"
        r = client.post(
            "/api/auth/register",
            json={"name": "Тест Юзер", "email": email, "password": "Passw0rd!"},
        )
        assert r.status_code == 200, r.text
        return r.json()["token"], r.json()["user"]["id"]

    return _make


@pytest.fixture()
def admin_token(client):
    """Токен посеянного администратора."""
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@mediahub.ru", "password": "admin123!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def group_with_post(client, make_user):
    """Пользователь + своя группа + черновик в ней."""
    token, uid = make_user("owner")
    g = client.post(
        "/api/groups",
        json={"name": f"Группа {uuid.uuid4().hex[:6]}", "description": ""},
        headers=auth(token),
    )
    assert g.status_code == 200, g.text
    gid = g.json()["id"]
    p = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": f"Пост {uuid.uuid4().hex[:6]}", "content": "текст", "status": "draft"},
        headers=auth(token),
    )
    assert p.status_code == 200, p.text
    return {"token": token, "user_id": uid, "group_id": gid, "post": p.json()}
