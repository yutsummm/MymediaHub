"""
Загруженные файлы не должны отдаваться кому попало.

Раньше /uploads раздавался StaticFiles без единой проверки: кто знал URL, тот
скачивал файл, и медиа закрытых групп были фактически публичны. Заголовок
авторизации к <img src="..."> не приложить, поэтому право доступа несёт подпись
в самой ссылке — её выдаёт API тому, кто уже видит содержащую запись.
"""
import io
import json
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import auth

from utils import sign_upload_url, upload_filename


def upload_image(client, token, name="pic.png"):
    """Загружает картинку и отдаёт ответ ручки (url уже подписан)."""
    r = client.post(
        "/api/upload",
        files={"file": (name, io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64), "image/png")},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


def parts(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    return parsed.path, {k: v[0] for k, v in parse_qs(parsed.query).items()}


# ── Сама раздача ─────────────────────────────────────────────────────────────

def test_unsigned_url_is_rejected(client, admin_token):
    """Главное свойство: голая ссылка на файл больше не работает."""
    media = upload_image(client, admin_token)
    path, _ = parts(media["url"])
    assert client.get(path).status_code == 403


def test_signed_url_serves_the_file(client, admin_token):
    media = upload_image(client, admin_token)
    r = client.get(media["url"])
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_signature_is_required_in_full(client, admin_token):
    """Половины подписи недостаточно — оба параметра обязательны."""
    media = upload_image(client, admin_token)
    path, q = parts(media["url"])
    assert client.get(f"{path}?exp={q['exp']}").status_code == 403
    assert client.get(f"{path}?sig={q['sig']}").status_code == 403


def test_tampered_signature_is_rejected(client, admin_token):
    media = upload_image(client, admin_token)
    path, q = parts(media["url"])
    broken = ("0" if q["sig"][0] != "0" else "1") + q["sig"][1:]
    assert client.get(f"{path}?exp={q['exp']}&sig={broken}").status_code == 403


def test_extending_expiry_invalidates_signature(client, admin_token):
    """Подпись считается вместе со сроком — продлить его в обход нельзя."""
    media = upload_image(client, admin_token)
    path, q = parts(media["url"])
    longer = int(q["exp"]) + 10 * 365 * 24 * 3600
    assert client.get(f"{path}?exp={longer}&sig={q['sig']}").status_code == 403


def test_signature_does_not_transfer_between_files(client, admin_token):
    """Подпись одного файла не должна открывать другой."""
    first = upload_image(client, admin_token, "one.png")
    second = upload_image(client, admin_token, "two.png")
    path_second, _ = parts(second["url"])
    _, q_first = parts(first["url"])
    r = client.get(f"{path_second}?exp={q_first['exp']}&sig={q_first['sig']}")
    assert r.status_code == 403


def test_expired_signature_is_rejected(client, admin_token, monkeypatch):
    import utils

    media = upload_image(client, admin_token)
    name = upload_filename(media["url"])
    monkeypatch.setattr(utils, "UPLOAD_URL_TTL", -60)
    stale = sign_upload_url(f"/uploads/{name}")
    r = client.get(stale)
    assert r.status_code == 410, "просроченную ссылку надо отличать от поддельной"


def test_missing_file_is_404_not_403(client, admin_token):
    """Действующая подпись на несуществующий файл — это 404, а не отказ."""
    signed = sign_upload_url("/uploads/deadbeef.png")
    assert client.get(signed).status_code == 404


@pytest.mark.parametrize(
    "name",
    ["....png", "..%2F..%2Fetc%2Fpasswd", "%2e%2e%2fmain.py"],
)
def test_path_traversal_does_not_escape_upload_dir(client, name):
    """Даже с любой подписью выйти за каталог загрузок нельзя."""
    r = client.get(f"/uploads/{name}?exp=99999999999&sig=" + "0" * 32)
    assert r.status_code in (403, 404)
    assert b"DATABASE" not in r.content


# ── Подпись в ответах API ────────────────────────────────────────────────────

def test_post_media_comes_back_signed_and_openable(client, group_with_post, admin_token):
    """Медиа поста уходит наружу подписанным и сразу открывается."""
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    media = upload_image(client, token)

    created = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "С картинкой", "content": "текст", "media": [media]},
        headers=auth(token),
    )
    assert created.status_code == 200, created.text
    url = created.json()["media"][0]["url"]
    assert "sig=" in url, "ссылка должна возвращаться подписанной"
    assert client.get(url).status_code == 200

    # И при повторном чтении поста — тоже
    pid = created.json()["id"]
    again = client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(token))
    assert client.get(again.json()["media"][0]["url"]).status_code == 200


def test_database_stores_url_without_signature(client, group_with_post):
    """
    В базу подпись попадать не должна. Фронт присылает медиа ровно в том виде,
    в каком получил, — если не срезать, в базе осядет протухшая ссылка и та же
    картинка перестанет открываться.
    """
    from utils import get_db

    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    media = upload_image(client, token)
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Хранение", "content": "текст", "media": [media]},
        headers=auth(token),
    ).json()["id"]

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT media FROM posts WHERE id=%s", (pid,))
    stored = json.loads(c.fetchone()["media"])
    conn.close()

    assert stored[0]["url"] == f"/uploads/{upload_filename(media['url'])}"
    assert "sig=" not in stored[0]["url"]
    assert "exp=" not in stored[0]["url"]


def test_resaving_post_does_not_accumulate_signatures(client, group_with_post):
    """Пост можно пересохранять сколько угодно — ссылка не должна распухать."""
    from utils import get_db

    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    media = upload_image(client, token)
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Круг", "content": "т", "media": [media]},
        headers=auth(token),
    ).json()["id"]

    for _ in range(3):
        current = client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(token)).json()
        r = client.put(
            f"/api/groups/{gid}/posts/{pid}",
            json={"media": current["media"]},
            headers=auth(token),
        )
        assert r.status_code == 200

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT media FROM posts WHERE id=%s", (pid,))
    stored = json.loads(c.fetchone()["media"])
    conn.close()
    assert stored[0]["url"] == f"/uploads/{upload_filename(media['url'])}"
    assert client.get(
        client.get(f"/api/groups/{gid}/posts/{pid}", headers=auth(token)).json()["media"][0]["url"]
    ).status_code == 200


def test_volunteer_media_comes_back_signed(client, group_with_post):
    token = group_with_post["token"]
    gid = group_with_post["group_id"]
    media = upload_image(client, token)

    created = client.post(
        f"/api/groups/{gid}/volunteer-media",
        json={"event_name": "Субботник", "media": [media]},
        headers=auth(token),
    )
    assert created.status_code == 200, created.text
    assert "sig=" in created.json()["media"][0]["url"]

    listing = client.get(f"/api/groups/{gid}/volunteer-media", headers=auth(token))
    url = listing.json()["items"][0]["media"][0]["url"]
    assert "sig=" in url
    assert client.get(url).status_code == 200
