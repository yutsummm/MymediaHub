"""
Каждый /api-роут обязан требовать токен. Список публичных ручек задан явно —
если кто-то добавит новый роут и забудет Depends(get_current_user_id),
тест упадёт сам, без ручного перечисления путей.
"""
import pytest

from utils import current_session, get_current_user_id

# (метод, путь) — единственные ручки, работающие без авторизации.
PUBLIC_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    ("GET", "/api/invites/{token}"),
    # Мониторинг ходит без токена. Наружу уходят только флаги и счётчики.
    ("GET", "/api/health"),
}


# current_session — та же авторизация, только отдаёт ещё и идентификатор сессии:
# он нужен ручкам выхода, чтобы погасить именно этот токен.
AUTH_DEPENDENCIES = (get_current_user_id, current_session)


def _uses_auth(dependant) -> bool:
    if dependant.call in AUTH_DEPENDENCIES:
        return True
    return any(_uses_auth(d) for d in dependant.dependencies)


def _api_routes(app):
    for route in app.routes:
        if not hasattr(route, "methods") or not route.path.startswith("/api"):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            yield method, route.path, route


def test_route_inventory_is_not_empty(app):
    assert len(list(_api_routes(app))) > 50


def test_every_route_declares_expected_auth(app):
    """Непубличные роуты объявляют зависимость авторизации, публичные — нет."""
    wrong_open, wrong_closed = [], []
    for method, path, route in _api_routes(app):
        has_auth = _uses_auth(route.dependant)
        is_public = (method, path) in PUBLIC_ROUTES
        if is_public and has_auth:
            wrong_closed.append(f"{method} {path}")
        elif not is_public and not has_auth:
            wrong_open.append(f"{method} {path}")

    assert not wrong_open, f"роуты без авторизации: {wrong_open}"
    assert not wrong_closed, f"публичные роуты неожиданно требуют токен: {wrong_closed}"


PROTECTED_CALLS = [
    ("get", "/api/users"),
    ("post", "/api/users"),
    ("delete", "/api/users/1"),
    ("put", "/api/users/1/role"),
    ("get", "/api/posts"),
    ("post", "/api/posts"),
    ("get", "/api/posts/1"),
    ("put", "/api/posts/1"),
    ("delete", "/api/posts/1"),
    ("post", "/api/posts/1/publish"),
    ("post", "/api/posts/sync-vk-stats"),
    ("get", "/api/settings/vk"),
    ("post", "/api/settings/vk"),
    ("delete", "/api/settings/vk"),
    ("get", "/api/settings/telegram"),
    ("delete", "/api/settings/telegram"),
    ("post", "/api/vk/oauth-exchange"),
    ("get", "/api/analytics/summary"),
    ("get", "/api/analytics/timeline"),
    ("get", "/api/analytics/export?start_date=2024-01-01&end_date=2024-01-02"),
    ("get", "/api/calendar?start=2024-01-01&end=2024-12-31"),
    ("get", "/api/templates"),
    ("post", "/api/generate-text"),
    ("post", "/api/ai-enhance"),
    ("post", "/api/upload"),
    ("get", "/api/youth-centers?lat=56&lon=92"),
    ("get", "/api/notifications"),
    ("put", "/api/notifications/1/read"),
    ("get", "/api/groups"),
    ("post", "/api/groups"),
]


@pytest.mark.parametrize("method,path", PROTECTED_CALLS)
def test_returns_401_without_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED_CALLS)
def test_returns_401_with_garbage_token(client, method, path):
    r = getattr(client, method)(path, headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_login_works_without_token(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@mediahub.ru", "password": "admin123!"},
    )
    assert r.status_code == 200
    assert r.json()["token"]


def test_login_rejects_wrong_password(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@mediahub.ru", "password": "неверный"},
    )
    assert r.status_code == 401
