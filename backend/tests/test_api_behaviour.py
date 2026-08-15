"""Базовые рабочие сценарии: регистрация, посты, группы, шаблоны, загрузка."""
import io

import pytest
from conftest import auth

# ── Регистрация ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "password,reason",
    [
        ("short1!", "короче 8 символов"),
        ("12345678!", "без букв"),
        ("password123", "без спецсимвола"),
    ],
)
def test_register_rejects_weak_password(client, password, reason):
    r = client.post(
        "/api/auth/register",
        json={"name": "Слабый", "email": "weak@test.local", "password": password},
    )
    assert r.status_code == 400, reason


def test_register_rejects_duplicate_email(client, make_user):
    token, uid = make_user("dup")
    email = client.get("/api/groups", headers=auth(token))  # токен валиден
    assert email.status_code == 200
    r = client.post(
        "/api/auth/register",
        json={"name": "Дубль", "email": "admin@mediahub.ru", "password": "Passw0rd!"},
    )
    assert r.status_code == 409


def test_new_user_joins_default_group(client, make_user):
    token, _ = make_user("joiner")
    groups = client.get("/api/groups", headers=auth(token)).json()
    assert len(groups) >= 1


# ── Посты ────────────────────────────────────────────────────────────────────

def test_group_post_crud_roundtrip(client, group_with_post):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    pid = group_with_post["post"]["id"]

    r = client.put(
        f"/api/groups/{gid}/posts/{pid}",
        json={"title": "Обновлённый", "tags": ["мероприятия"]},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Обновлённый"
    assert r.json()["tags"] == ["мероприятия"]

    assert client.delete(f"/api/groups/{gid}/posts/{pid}", headers=auth(token)).status_code == 200
    assert client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(token)).status_code == 404


def test_post_list_filters_by_status(client, group_with_post):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    r = client.get(f"/api/groups/{gid}/posts?status=draft", headers=auth(token))
    assert r.status_code == 200
    assert all(p["status"] == "draft" for p in r.json()["posts"])


def test_json_fields_roundtrip_as_lists(client, group_with_post):
    """platforms/tags/media хранятся строками в БД, но наружу должны идти списками."""
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    r = client.post(
        f"/api/groups/{gid}/posts",
        json={
            "title": "С платформами",
            "content": "x",
            "platforms": ["vk", "telegram"],
            "tags": ["новости"],
        },
        headers=auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["platforms"] == ["vk", "telegram"]
    assert body["tags"] == ["новости"]
    assert isinstance(body["media"], list)


def test_missing_post_returns_404(client, group_with_post):
    token = group_with_post["token"]
    assert client.get("/api/posts/99999999", headers=auth(token)).status_code == 404


# ── Группы и инвайты ─────────────────────────────────────────────────────────

def test_invite_flow_adds_member(client, admin_token, make_user):
    token, uid = make_user("invitee")
    gid = client.post(
        "/api/groups", json={"name": "Приглашающая", "description": ""}, headers=auth(admin_token)
    ).json()["id"]

    invite = client.post(
        f"/api/groups/{gid}/invites",
        json={"role": "editor", "expires_hours": 24, "max_uses": 5},
        headers=auth(admin_token),
    ).json()

    preview = client.get(f"/api/invites/{invite['token']}")
    assert preview.status_code == 200

    assert client.post(f"/api/invites/{invite['token']}/accept", headers=auth(token)).status_code == 200
    members = client.get(f"/api/groups/{gid}/members", headers=auth(admin_token)).json()
    assert uid in [m["user_id"] if "user_id" in m else m["id"] for m in members]


def test_invalid_invite_token_returns_404(client):
    assert client.get("/api/invites/несуществующий").status_code == 404


# ── Шаблоны ──────────────────────────────────────────────────────────────────

def test_templates_expose_parsed_fields(client, admin_token):
    r = client.get("/api/templates", headers=auth(admin_token))
    assert r.status_code == 200
    templates = r.json()
    assert templates
    assert all(isinstance(t["fields"], list) for t in templates)


def test_generate_text_substitutes_placeholders(client, admin_token):
    r = client.post(
        "/api/generate-text",
        json={"template_type": "announcement", "fields": {"event_name": "Хакатон"}},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert "Хакатон" in r.json()["text"]
    assert "{event_name}" not in r.json()["text"]


def test_generate_text_unknown_template_returns_404(client, admin_token):
    r = client.post(
        "/api/generate-text",
        json={"template_type": "нет-такого", "fields": {}},
        headers=auth(admin_token),
    )
    assert r.status_code == 404


def test_ai_enhance_rejects_unknown_mode(client, admin_token):
    r = client.post(
        "/api/ai-enhance", json={"text": "текст", "mode": "нет-такого"}, headers=auth(admin_token)
    )
    assert r.status_code == 400


def test_ai_enhance_rejects_empty_text(client, admin_token):
    r = client.post(
        "/api/ai-enhance", json={"text": "   ", "mode": "creative"}, headers=auth(admin_token)
    )
    assert r.status_code == 400


# ── Загрузка файлов ──────────────────────────────────────────────────────────

def test_upload_rejects_unsupported_type(client, admin_token):
    r = client.post(
        "/api/upload",
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
        headers=auth(admin_token),
    )
    assert r.status_code == 400


def test_upload_accepts_image(client, admin_token):
    r = client.post(
        "/api/upload",
        files={"file": ("pic.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64), "image/png")},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "image"
    assert body["url"].startswith("/uploads/")


# ── Аналитика и календарь ────────────────────────────────────────────────────

def test_analytics_summary_shape(client, admin_token):
    r = client.get("/api/analytics/summary", headers=auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    for key in ("total_posts", "published", "scheduled", "drafts", "top_posts", "platform_stats"):
        assert key in body


def test_platform_stats_hide_numbers_for_telegram(client, admin_token):
    """
    Колонки views/reactions одни на все площадки и заполняются только синхронизацией
    ВК. Раньше строка Telegram показывала эти же числа, выдавая вконтактовские
    просмотры за телеграмные. Теперь по таким площадкам должно быть null.
    """
    stats = client.get("/api/analytics/summary", headers=auth(admin_token)).json()["platform_stats"]
    by_platform = {p["platform"]: p for p in stats}

    assert by_platform["vk"]["stats_available"] is True
    assert isinstance(by_platform["vk"]["views"], int)

    tg = by_platform["telegram"]
    assert tg["stats_available"] is False
    assert tg["views"] is None, "по Telegram нельзя показывать числа из VK"
    assert tg["reactions"] is None
    # Количество публикаций известно достоверно и остаётся числом
    assert isinstance(tg["count"], int)


def test_top_posts_expose_vk_post_id(client, admin_token):
    """Фронт по этому полю решает, показывать цифры или «нет данных»."""
    top = client.get("/api/analytics/summary", headers=auth(admin_token)).json()["top_posts"]
    assert top, "в посевных данных должны быть опубликованные посты"
    assert all("vk_post_id" in p for p in top)


def test_analytics_timeline_length_matches_period(client, admin_token):
    r = client.get("/api/analytics/timeline?period=week", headers=auth(admin_token))
    assert r.status_code == 200
    assert len(r.json()) == 7


def test_analytics_export_rejects_bad_dates(client, admin_token):
    r = client.get(
        "/api/analytics/export?start_date=01-01-2024&end_date=2024-01-02", headers=auth(admin_token)
    )
    assert r.status_code == 400


def test_analytics_export_returns_xlsx(client, admin_token):
    r = client.get(
        "/api/analytics/export?start_date=2024-01-01&end_date=2024-01-31", headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_youth_centers_sorted_by_distance(client, admin_token):
    r = client.get("/api/youth-centers?lat=56.01&lon=92.87", headers=auth(admin_token))
    assert r.status_code == 200
    distances = [c["distance_km"] for c in r.json()]
    assert distances == sorted(distances)
