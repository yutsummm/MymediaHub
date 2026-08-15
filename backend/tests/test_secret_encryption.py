"""
Токены соцсетей не должны лежать в базе открытым текстом.

vk_settings.access_token и tg_settings.bot_token — это полный доступ к пабликам
организации: утечка дампа отдавала их целиком. Теперь пишем шифрованными, а
читаем через decrypt_secret.
"""
import pytest
from conftest import auth

from utils import SECRET_PREFIX, decrypt_secret, encrypt_secret


def stored_secret(table: str, column: str, where: str = "id=1"):
    from utils import get_db

    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT {column} AS v FROM {table} WHERE {where}")  # noqa: S608 — имена таблиц свои
    row = c.fetchone()
    conn.close()
    return row["v"] if row else None


# ── Сами примитивы ───────────────────────────────────────────────────────────

def test_roundtrip_returns_original():
    token = "vk1.a.ОченьДлинныйТокен-123"
    assert decrypt_secret(encrypt_secret(token)) == token


def test_ciphertext_does_not_contain_plaintext():
    token = "secret-bot-token-42"
    blob = encrypt_secret(token)
    assert blob.startswith(SECRET_PREFIX)
    assert token not in blob


def test_encryption_is_not_deterministic():
    """Одинаковые токены не должны давать одинаковый шифротекст."""
    assert encrypt_secret("одно и то же") != encrypt_secret("одно и то же")


@pytest.mark.parametrize("value", [None, ""])
def test_empty_values_pass_through(value):
    assert encrypt_secret(value) == value
    assert decrypt_secret(value) == value


def test_double_encryption_is_noop():
    """Повторный проход по уже зашифрованному значению не должен его портить."""
    once = encrypt_secret("токен")
    assert encrypt_secret(once) == once
    assert decrypt_secret(once) == "токен"


def test_legacy_plaintext_is_returned_as_is():
    """
    В базе остаются строки, записанные до включения шифрования. Ломать на них
    публикацию нельзя — они дошифруются при следующем сохранении настроек.
    """
    assert decrypt_secret("голый-токен-из-старой-базы") == "голый-токен-из-старой-базы"


def test_broken_ciphertext_fails_loudly():
    """Молча отдавать мусор в VK нельзя — лучше внятная ошибка."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        decrypt_secret(SECRET_PREFIX + "не-шифротекст")
    assert e.value.status_code == 500


def test_key_is_derived_from_jwt_secret(monkeypatch):
    """
    Отдельного TOKEN_ENCRYPTION_KEY на существующих окружениях нет, поэтому
    ключ выводится из JWT_SECRET. Проверяем, что связь настоящая: с другим
    JWT_SECRET расшифровать не выходит.
    """
    from fastapi import HTTPException

    import utils

    blob = encrypt_secret("токен")
    monkeypatch.setattr(utils, "JWT_SECRET", "совершенно-другой-секрет")
    with pytest.raises(HTTPException) as e:
        decrypt_secret(blob)
    assert e.value.status_code == 500


# ── Через настоящие ручки ────────────────────────────────────────────────────

def test_tg_token_is_stored_encrypted(client, admin_token, monkeypatch):
    """Сохранение настроек Telegram кладёт в базу шифротекст, а не сам токен."""
    import routers.settings as settings_router

    monkeypatch.setattr(settings_router, "tg_get_chat_title", lambda *a, **kw: "Тестовый канал")
    secret = "123456:ОченьСекретныйБотовыйТокен"

    r = client.post(
        "/api/settings/telegram",
        json={"bot_token": secret, "chat_id": "@test_channel"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text

    stored = stored_secret("tg_settings", "bot_token")
    assert stored is not None
    assert stored != secret, "токен лежит в базе открытым текстом"
    assert stored.startswith(SECRET_PREFIX)
    assert decrypt_secret(stored) == secret, "и при этом должен читаться обратно"


def test_group_tg_token_is_stored_encrypted(client, admin_token, monkeypatch):
    """Групповые настройки — отдельный путь записи, его тоже надо стеречь."""
    import routers.settings as settings_router

    monkeypatch.setattr(settings_router, "tg_get_chat_title", lambda *a, **kw: "Канал группы")

    gid = client.post(
        "/api/groups", json={"name": "С телеграмом", "description": ""}, headers=auth(admin_token)
    ).json()["id"]
    secret = "654321:ТокенГрупповогоБота"

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "result": {"title": "Канал группы"}}

    monkeypatch.setattr(settings_router.http_requests, "get", lambda *a, **kw: FakeResponse())

    r = client.post(
        f"/api/groups/{gid}/settings/telegram",
        json={"bot_token": secret, "chat_id": "@group_channel"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text

    stored = stored_secret("tg_settings", "bot_token", f"workspace_id={gid}")
    assert stored.startswith(SECRET_PREFIX)
    assert decrypt_secret(stored) == secret


def test_vk_token_is_stored_encrypted(client, admin_token, monkeypatch):
    import routers.settings as settings_router

    monkeypatch.setattr(settings_router, "vk_get_group_name", lambda *a, **kw: "Тестовый паблик")
    secret = "vk1.a.ОченьСекретныйТокенСообщества"

    r = client.post(
        "/api/settings/vk",
        json={"group_id": "-123456", "access_token": secret},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text

    stored = stored_secret("vk_settings", "access_token")
    assert stored != secret, "токен лежит в базе открытым текстом"
    assert stored.startswith(SECRET_PREFIX)
    assert decrypt_secret(stored) == secret


def test_startup_encrypts_legacy_plaintext_tokens(client, admin_token, monkeypatch):
    """
    Токены, записанные до включения шифрования, дошифровываются при старте.
    Читать открытый текст мы умеем, но оставлять его в базе — ровно та проблема,
    ради которой всё затевалось.
    """
    import main
    import routers.settings as settings_router
    from utils import get_db

    monkeypatch.setattr(settings_router, "tg_get_chat_title", lambda *a, **kw: "Канал")
    client.post(
        "/api/settings/telegram",
        json={"bot_token": "любой", "chat_id": "@c"},
        headers=auth(admin_token),
    )

    # Возвращаем строку в «дошифровочное» состояние
    legacy = "987654:СтарыйГолыйТокен"
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE tg_settings SET bot_token=%s WHERE id=1", (legacy,))
    conn.commit()
    conn.close()
    assert stored_secret("tg_settings", "bot_token") == legacy

    main.encrypt_existing_secrets()

    stored = stored_secret("tg_settings", "bot_token")
    assert stored.startswith(SECRET_PREFIX), "открытый токен должен был зашифроваться"
    assert decrypt_secret(stored) == legacy, "и остаться тем же самым токеном"

    # Идемпотентность: второй прогон не должен шифровать повторно
    main.encrypt_existing_secrets()
    assert stored_secret("tg_settings", "bot_token") == stored


def test_settings_endpoints_never_expose_token(client, admin_token, monkeypatch):
    """Наружу токен не отдаём ни в каком виде — ни открытый, ни шифротекст."""
    import routers.settings as settings_router

    monkeypatch.setattr(settings_router, "vk_get_group_name", lambda *a, **kw: "Паблик")
    secret = "vk1.a.НеДолженПопастьВОтвет"
    client.post(
        "/api/settings/vk",
        json={"group_id": "-777", "access_token": secret},
        headers=auth(admin_token),
    )

    body = client.get("/api/settings/vk", headers=auth(admin_token)).text
    assert secret not in body
    assert "access_token" not in body
    assert SECRET_PREFIX not in body
