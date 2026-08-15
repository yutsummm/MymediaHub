"""
Интеграции должны подключаться больше чем к одной группе.

id у vk_settings/tg_settings был объявлен как INTEGER DEFAULT 1 без
последовательности: глобальные настройки пишутся с явным id=1, групповые id не
указывают и получали тот же самый. Вторая интеграция падала с UniqueViolation —
подключить Telegram к двум группам было невозможно.
"""
import uuid

import pytest
from conftest import auth


@pytest.fixture()
def fake_telegram(monkeypatch):
    """Наружу в Telegram ходить не надо — подменяем обе точки проверки чата."""
    import routers.settings as settings_router

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "result": {"title": "Канал"}}

    monkeypatch.setattr(settings_router, "tg_get_chat_title", lambda *a, **kw: "Канал")
    monkeypatch.setattr(settings_router.http_requests, "get", lambda *a, **kw: FakeResponse())


def make_group(client, token):
    return client.post(
        "/api/groups",
        json={"name": f"Группа {uuid.uuid4().hex[:6]}", "description": ""},
        headers=auth(token),
    ).json()["id"]


def test_telegram_connects_to_two_groups(client, admin_token, fake_telegram):
    first, second = make_group(client, admin_token), make_group(client, admin_token)

    for gid, token in ((first, "111:ПервыйБот"), (second, "222:ВторойБот")):
        r = client.post(
            f"/api/groups/{gid}/settings/telegram",
            json={"bot_token": token, "chat_id": f"@chat_{gid}"},
            headers=auth(admin_token),
        )
        assert r.status_code == 200, f"группа {gid}: {r.text}"

    from utils import decrypt_secret, get_db

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT workspace_id, bot_token FROM tg_settings WHERE workspace_id IN %s",
        ((first, second),),
    )
    rows = {r["workspace_id"]: decrypt_secret(r["bot_token"]) for r in c.fetchall()}
    conn.close()

    assert rows == {first: "111:ПервыйБот", second: "222:ВторойБот"}, (
        "у каждой группы должна быть своя запись со своим токеном"
    )


def test_vk_connects_to_two_groups(client, admin_token, monkeypatch):
    import routers.settings as settings_router

    monkeypatch.setattr(settings_router, "vk_get_group_name", lambda *a, **kw: "Паблик")

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"response": [{"id": 1, "name": "Паблик"}]}

    monkeypatch.setattr(settings_router.http_requests, "get", lambda *a, **kw: FakeResponse())

    first, second = make_group(client, admin_token), make_group(client, admin_token)
    for gid, token in ((first, "vk1.a.Первый"), (second, "vk1.a.Второй")):
        r = client.post(
            f"/api/groups/{gid}/settings/vk",
            json={"group_id": f"-{gid}", "access_token": token},
            headers=auth(admin_token),
        )
        assert r.status_code == 200, f"группа {gid}: {r.text}"

    from utils import decrypt_secret, get_db

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT workspace_id, access_token FROM vk_settings WHERE workspace_id IN %s",
        ((first, second),),
    )
    rows = {r["workspace_id"]: decrypt_secret(r["access_token"]) for r in c.fetchall()}
    conn.close()

    assert rows == {first: "vk1.a.Первый", second: "vk1.a.Второй"}
