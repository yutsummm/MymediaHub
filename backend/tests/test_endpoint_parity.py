"""
Глобальные и групповые ручки не должны расходиться.

В проекте два параллельных набора: легаси-глобальный (`/api/posts`,
`/api/settings/vk`) и групповой. Удалить глобальный нельзя — на нём работают
пользователи без группы, а после отмены автовступления это все новички.
Но пока это были две копии кода, они уже успели разъехаться: глобальное
подключение Telegram отвергало неверный токен, а групповое молча его сохраняло.

Теперь логика общая, а эти тесты стерегут, что поведение совпадает.
"""
import pytest
from conftest import auth

import routers.analytics as analytics
import routers.settings as settings


@pytest.fixture()
def fake_socials(monkeypatch):
    """Наружу не ходим: проверяем поведение ручек, а не соцсети."""
    monkeypatch.setattr(settings, "vk_get_group_name", lambda *a, **kw: "Паблик")
    monkeypatch.setattr(settings, "tg_get_chat_title", lambda *a, **kw: "Канал")


# ── Одна реализация на оба набора ────────────────────────────────────────────

def test_analytics_routes_share_one_implementation():
    """
    Раньше отчёты были парой дословных копий на каждый: правку вносили в одну и
    забывали про вторую. Теперь различие сведено к области выборки.
    """
    import inspect

    for core in (analytics._summary, analytics._timeline, analytics._export):
        params = inspect.signature(core).parameters
        assert "where" in params and "params" in params, (
            f"{core.__name__} должна принимать область выборки, а не знать про группы"
        )


def test_settings_routes_share_one_implementation():
    import inspect

    for core in (settings._save_vk, settings._save_tg):
        assert "gid" in inspect.signature(core).parameters


# ── Совпадение поведения ─────────────────────────────────────────────────────

def test_analytics_summary_has_same_shape(client, group_with_post, admin_token):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    globally = client.get("/api/analytics/summary", headers=auth(token)).json()
    in_group = client.get(f"/api/groups/{gid}/analytics/summary", headers=auth(token)).json()
    assert set(globally) == set(in_group), "наборы полей должны совпадать"
    assert {p["platform"] for p in globally["platform_stats"]} == \
           {p["platform"] for p in in_group["platform_stats"]}


def test_analytics_timeline_has_same_shape(client, group_with_post):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    globally = client.get("/api/analytics/timeline?period=week", headers=auth(token)).json()
    in_group = client.get(
        f"/api/groups/{gid}/analytics/timeline?period=week", headers=auth(token)
    ).json()
    assert len(globally) == len(in_group) == 7
    assert set(globally[0]) == set(in_group[0])


def test_both_exports_produce_a_file(client, group_with_post):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    for path in ("/api/analytics/export", f"/api/groups/{gid}/analytics/export"):
        r = client.get(f"{path}?start_date=2024-01-01&end_date=2030-01-31", headers=auth(token))
        assert r.status_code == 200, path
        assert "spreadsheetml" in r.headers["content-type"]


@pytest.mark.parametrize("path", ["/api/analytics/export", "/api/groups/{gid}/analytics/export"])
def test_both_exports_reject_bad_dates(client, group_with_post, path):
    token = group_with_post["token"]
    url = path.format(gid=group_with_post["group_id"])
    r = client.get(f"{url}?start_date=01-01-2024&end_date=2024-01-02", headers=auth(token))
    assert r.status_code == 400


# ── Настройки: расхождение, которое уже случилось ────────────────────────────

def test_both_telegram_routes_reject_bad_token(client, group_with_post, admin_token, monkeypatch):
    """
    Ровно та разница, которую копии успели накопить: глобальная ручка неверный
    токен отвергала, а групповая молча сохраняла — и публикация потом тихо
    не работала.
    """
    def refuse(*a, **kw):
        raise ValueError("Unauthorized")

    monkeypatch.setattr(settings, "tg_get_chat_title", refuse)
    gid = group_with_post["group_id"]

    assert client.post(
        "/api/settings/telegram",
        json={"bot_token": "плохой", "chat_id": "@c"}, headers=auth(admin_token),
    ).status_code == 400
    assert client.post(
        f"/api/groups/{gid}/settings/telegram",
        json={"bot_token": "плохой", "chat_id": "@c"},
        headers=auth(group_with_post["token"]),
    ).status_code == 400, "групповая ручка должна вести себя так же"


def test_both_telegram_routes_survive_unreachable_telegram(
    client, group_with_post, admin_token, monkeypatch
):
    """
    А вот недоступность сети — не повод отказывать: у закрытых каналов getChat
    может не отвечать по причинам, не связанным с токеном.
    """
    def offline(*a, **kw):
        raise ConnectionError("сеть недоступна")

    monkeypatch.setattr(settings, "tg_get_chat_title", offline)
    gid = group_with_post["group_id"]

    r = client.post(
        f"/api/groups/{gid}/settings/telegram",
        json={"bot_token": "111:Токен", "chat_id": "@channel"},
        headers=auth(group_with_post["token"]),
    )
    assert r.status_code == 200
    assert r.json()["chat_title"] == "@channel", "название подставляется из chat_id"


def test_settings_shapes_match(client, group_with_post, admin_token, fake_socials):
    gid = group_with_post["group_id"]
    client.post("/api/settings/vk", json={"group_id": "-1", "access_token": "t"},
                headers=auth(admin_token))
    client.post(f"/api/groups/{gid}/settings/vk", json={"group_id": "-2", "access_token": "t"},
                headers=auth(group_with_post["token"]))

    globally = client.get("/api/settings/vk", headers=auth(admin_token)).json()
    in_group = client.get(f"/api/groups/{gid}/settings/vk",
                          headers=auth(group_with_post["token"])).json()
    assert set(globally) == set(in_group)
    assert "access_token" not in globally and "access_token" not in in_group


def test_disconnected_settings_answer_the_same(client, group_with_post, admin_token):
    gid = group_with_post["group_id"]
    client.delete("/api/settings/telegram", headers=auth(admin_token))
    client.delete(f"/api/groups/{gid}/settings/telegram", headers=auth(group_with_post["token"]))
    assert client.get("/api/settings/telegram", headers=auth(admin_token)).json() == \
           {"connected": False}
    assert client.get(f"/api/groups/{gid}/settings/telegram",
                      headers=auth(group_with_post["token"])).json() == {"connected": False}


def test_global_and_group_settings_are_separate_rows(client, group_with_post, admin_token, fake_socials):
    """
    Общая реализация не должна склеить хранилища: глобальная настройка живёт в
    строке id=1, групповая — в своей.
    """
    gid = group_with_post["group_id"]
    client.post("/api/settings/vk", json={"group_id": "-111", "access_token": "t"},
                headers=auth(admin_token))
    client.post(f"/api/groups/{gid}/settings/vk", json={"group_id": "-222", "access_token": "t"},
                headers=auth(group_with_post["token"]))

    assert client.get("/api/settings/vk", headers=auth(admin_token)).json()["group_id"] == "111"
    assert client.get(f"/api/groups/{gid}/settings/vk",
                      headers=auth(group_with_post["token"])).json()["group_id"] == "222"


# ── Права ────────────────────────────────────────────────────────────────────

def test_global_settings_need_system_admin(client, group_with_post):
    """Глобальные настройки — за системным админом, групповые — за админом группы."""
    token = group_with_post["token"]
    assert client.get("/api/settings/vk", headers=auth(token)).status_code == 403
    assert client.get(f"/api/groups/{group_with_post['group_id']}/settings/vk",
                      headers=auth(token)).status_code == 200


def test_group_settings_need_group_admin(client, group_with_post, make_user, admin_token):
    gid = group_with_post["group_id"]
    guest_token, guest_id = make_user("volunteer-guest")
    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "volunteer", "expires_hours": 24, "max_uses": 1},
        headers=auth(group_with_post["token"]),
    ).json()
    client.post(f"/api/invites/{invite['token']}/accept", headers=auth(guest_token))

    r = client.post(
        f"/api/groups/{gid}/settings/vk",
        json={"group_id": "-1", "access_token": "t"}, headers=auth(guest_token),
    )
    assert r.status_code == 403
