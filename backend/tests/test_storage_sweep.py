"""
Уборка загруженных файлов.

Файлы не стирались никогда: во всём приложении не было ни одного места, где
файл удаляется с диска. Строка уходила, файл оставался; отклонённые
материалы — заведомо ненужные — лежали наравне с одобренными, а том всего
пять гигабайт.

Уборка сделана обходом, а не удалением в каждом месте, где что-то стирается:
удаление группы уносит её посты каскадом в самой базе, приложение об этом не
узнаёт вовсе, и поштучная уборка полной быть не может в принципе.

Три вещи, каждая из которых при ошибке стоит дорого и необратимо:

* **отсрочка** — между загрузкой файла и сохранением поста проходит время, и
  без неё обход удалял бы картинки прямо из-под редактора;
* **предохранитель** — пустой список ссылок означает либо пустую систему,
  либо сломанный запрос; во втором случае обход сотрёт хранилище целиком;
* **используемое не трогается** — один файл может быть и в загрузке
  волонтёра, и в опубликованном посте разом.
"""
import os
import time
import uuid

import pytest
from conftest import auth

import storage
import utils


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    """Свой каталог загрузок, чтобы не трогать настоящий."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(utils, "UPLOAD_DIR", str(d))
    monkeypatch.setattr(storage, "UPLOAD_DIR", str(d))
    return d


def put(uploads, ext: str = "jpg", *, age_hours: float = 48, data: bytes = b"proba") -> str:
    """
    Кладёт на диск файл с настоящим именем и нужным возрастом.

    Имя обязано быть таким, какое выдаёт загрузка: обход ходит только по своим
    именам и придуманное короткое просто не заметит.
    """
    name = f"{uuid.uuid4().hex}.{ext}"
    path = uploads / name
    path.write_bytes(data)
    old = time.time() - age_hours * 3600
    os.utime(path, (old, old))
    return name


def db():
    return utils.get_db()


# ── Осиротевшее убирается ───────────────────────────────────────────────────

def test_file_nobody_refers_to_is_removed(uploads, client):
    put(uploads)
    conn = db()
    try:
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result["deleted"] == 1
    assert not list(uploads.glob("*.jpg"))


def test_freed_space_is_reported(uploads, client):
    put(uploads, data=b"x" * 4096)
    conn = db()
    try:
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result["freed_bytes"] == 4096


# ── Отсрочка ────────────────────────────────────────────────────────────────

def test_freshly_uploaded_file_is_spared(uploads, client):
    """
    Человек загрузил картинку и пошёл писать текст. Ссылки на неё ещё нет
    нигде — и это нормальное состояние, а не мусор.
    """
    name = put(uploads, age_hours=0)
    conn = db()
    try:
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result["deleted"] == 0
    assert result["too_young"] == 1
    assert (uploads / name).exists()


# ── Используемое не трогается ───────────────────────────────────────────────

def test_file_used_by_a_post_stays(uploads, client, group_with_post):
    name = put(uploads)
    r = client.put(
        f"/api/posts/{group_with_post['post']['id']}",
        json={"media": [{"url": f"/uploads/{name}", "type": "image", "filename": "ф.jpg"}]},
        headers=auth(group_with_post["token"]),
    )
    assert r.status_code == 200, r.text
    conn = db()
    try:
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result["deleted"] == 0
    assert (uploads / name).exists()


def test_file_used_by_volunteer_upload_stays(uploads, client, group_with_post):
    name = put(uploads)
    r = client.post(
        f"/api/groups/{group_with_post['group_id']}/volunteer-media",
        json={"event_name": "Фестиваль",
              "media": [{"url": f"/uploads/{name}", "type": "image", "filename": "ф.jpg"}]},
        headers=auth(group_with_post["token"]),
    )
    assert r.status_code == 200, r.text
    conn = db()
    try:
        assert storage.sweep(conn)["deleted"] == 0
    finally:
        conn.close()
    assert (uploads / name).exists()


def test_signed_link_sent_back_still_counts_as_a_reference(uploads, client, group_with_post):
    """
    Наружу ссылки уходят подписанными, и интерфейс присылает их обратно ровно
    в том виде, в каком получил. Обход обязан узнать файл и в таком виде —
    иначе он сотрёт картинку, которая прямо сейчас видна в посте.
    """
    name = put(uploads)
    signed = utils.sign_upload_url(f"/uploads/{name}")
    assert signed and "?" in signed, "ссылка должна быть подписанной"

    r = client.put(
        f"/api/posts/{group_with_post['post']['id']}",
        json={"media": [{"url": signed, "type": "image", "filename": "ф.jpg"}]},
        headers=auth(group_with_post["token"]),
    )
    assert r.status_code == 200, r.text

    conn = db()
    try:
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result["deleted"] == 0
    assert (uploads / name).exists()


# ── Предохранитель ──────────────────────────────────────────────────────────

def test_sweep_refuses_to_run_when_references_look_broken(uploads, client,
                                                          group_with_post, monkeypatch):
    """
    Сломанный запрос ссылок выглядит как «в системе нет медиа». Разница видна
    только по тому, есть ли записи с медиа, — и в этом случае обход обязан
    отказаться работать, а не стереть хранилище.
    """
    name = put(uploads)
    client.put(
        f"/api/posts/{group_with_post['post']['id']}",
        json={"media": [{"url": f"/uploads/{name}", "type": "image", "filename": "ф.jpg"}]},
        headers=auth(group_with_post["token"]),
    )
    monkeypatch.setattr(storage, "referenced_urls", lambda conn: set())
    conn = db()
    try:
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result.get("aborted") is True
    assert result["deleted"] == 0
    assert (uploads / name).exists(), "предохранитель обязан сохранить файл"


def test_empty_system_sweeps_normally(uploads, client):
    """Пустой список ссылок при отсутствии записей — это просто пустая система."""
    conn = db()
    try:
        c = conn.cursor()
        c.execute("UPDATE posts SET media='[]'::jsonb")
        c.execute("UPDATE volunteer_media SET media='[]'::jsonb")
        conn.commit()
        put(uploads)
        result = storage.sweep(conn)
    finally:
        conn.close()
    assert result.get("aborted") is None
    assert result["deleted"] == 1


# ── Отклонённые загрузки ────────────────────────────────────────────────────

def test_rejected_uploads_are_purged_after_the_term(client, group_with_post):
    gid = group_with_post["group_id"]
    r = client.post(
        f"/api/groups/{gid}/volunteer-media",
        json={"event_name": "Старое", "media": [{"url": "/uploads/zzzzzzzz.jpg",
                                                 "type": "image", "filename": "ф.jpg"}]},
        headers=auth(group_with_post["token"]),
    )
    vid = r.json()["id"]
    client.put(f"/api/groups/{gid}/volunteer-media/{vid}/status",
               json={"status": "rejected"}, headers=auth(group_with_post["token"]))

    conn = db()
    try:
        c = conn.cursor()
        c.execute("UPDATE volunteer_media SET created_at = NOW() - INTERVAL '40 days' "
                  "WHERE id=%s", (vid,))
        conn.commit()
        assert storage.purge_rejected(conn, days=30) >= 1
        c.execute("SELECT 1 FROM volunteer_media WHERE id=%s", (vid,))
        assert c.fetchone() is None
    finally:
        conn.close()


def test_approved_and_pending_are_never_purged(client, group_with_post):
    gid = group_with_post["group_id"]
    kept = []
    for status in ("approved", "pending"):
        r = client.post(
            f"/api/groups/{gid}/volunteer-media",
            json={"event_name": f"Живое {status}",
                  "media": [{"url": "/uploads/yyyyyyyy.jpg", "type": "image", "filename": "ф.jpg"}]},
            headers=auth(group_with_post["token"]),
        )
        vid = r.json()["id"]
        if status != "pending":
            client.put(f"/api/groups/{gid}/volunteer-media/{vid}/status",
                       json={"status": status}, headers=auth(group_with_post["token"]))
        kept.append(vid)

    conn = db()
    try:
        c = conn.cursor()
        c.execute("UPDATE volunteer_media SET created_at = NOW() - INTERVAL '400 days' "
                  "WHERE id = ANY(%s)", (kept,))
        conn.commit()
        storage.purge_rejected(conn, days=30)
        c.execute("SELECT COUNT(*) AS n FROM volunteer_media WHERE id = ANY(%s)", (kept,))
        assert c.fetchone()["n"] == 2, "одобренное и ожидающее уборке не подлежат"
    finally:
        conn.close()


# ── Посторонние файлы ───────────────────────────────────────────────────────

def test_files_with_foreign_names_are_left_alone(uploads, client):
    """
    В каталоге могут лежать не наши файлы — например, служебные. Обход ходит
    только по тем именам, которые сам и выдаёт.
    """
    path = uploads / ".gitkeep"
    path.write_text("")
    old = time.time() - 100 * 3600
    os.utime(path, (old, old))
    conn = db()
    try:
        storage.sweep(conn)
    finally:
        conn.close()
    assert path.exists()
