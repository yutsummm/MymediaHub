"""
Публикация идёт через очередь.

Раньше отправка шла прямо внутри HTTP-запроса. Загрузка видео в ВК идёт с
таймаутом 120 секунд на файл, а файлов в посте может быть несколько — тяжёлый
пост либо подвешивал запрос, либо отваливался по таймауту прокси. Причём
отвалившийся запрос ничего не отменял: пост мог уже уйти в паблик, а человек
видел ошибку и жал «Опубликовать» ещё раз.
"""
import time

import pytest
from conftest import auth, drain_publish_queue

import publish_queue
from utils import get_db


def make_post(client, group, title="В очередь"):
    return client.post(
        f"/api/groups/{group['group_id']}/posts",
        json={"title": title, "content": "т", "platforms": []},
        headers=auth(group["token"]),
    ).json()["id"]


def jobs_for(post_id: int) -> list[dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM publish_jobs WHERE post_id=%s ORDER BY id", (post_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── Ручка отвечает сразу ─────────────────────────────────────────────────────

def test_publish_returns_immediately(client, group_with_post, monkeypatch):
    """
    Главное свойство: ручка не ждёт соцсети. Изображаем медленную отправку и
    проверяем, что ответ приходит мгновенно.
    """
    pid = make_post(client, group_with_post)

    def slow(*a, **kw):
        time.sleep(3)
        return {}

    monkeypatch.setattr(publish_queue, "perform_publish", slow)

    started = time.monotonic()
    r = client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    )
    elapsed = time.monotonic() - started

    assert r.status_code == 200
    assert elapsed < 1, f"ручка ждала отправки {elapsed:.1f} с вместо того, чтобы поставить в очередь"
    assert r.json()["state"] == "queued"
    assert r.json()["post_id"] == pid


def test_post_is_published_by_the_worker(client, group_with_post):
    pid = make_post(client, group_with_post)
    client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    )
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status FROM posts WHERE id=%s", (pid,))
    assert c.fetchone()["status"] != "published", "до воркера пост ещё не опубликован"
    conn.close()

    assert drain_publish_queue() >= 1
    assert jobs_for(pid)[-1]["state"] == "done"


# ── Защита от дублей ─────────────────────────────────────────────────────────

def test_second_click_does_not_create_second_job(client, group_with_post):
    """
    Два клика по «Опубликовать» не должны дать две записи на стене — отозвать
    их из ВК и Telegram нельзя.
    """
    pid = make_post(client, group_with_post)
    path = f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish"
    first = client.post(path, headers=auth(group_with_post["token"])).json()
    second = client.post(path, headers=auth(group_with_post["token"])).json()

    assert first["id"] == second["id"], "повторный клик должен вернуть ту же задачу"
    assert len(jobs_for(pid)) == 1


def test_one_job_goes_to_one_worker(client, group_with_post):
    """Две копии воркера не должны взять одну задачу."""
    pid = make_post(client, group_with_post)
    client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    )
    first_conn, second_conn = get_db(), get_db()
    try:
        first = publish_queue.claim_job(first_conn)
        second = publish_queue.claim_job(second_conn)
        assert first is not None
        assert second is None or second["id"] != first["id"]
    finally:
        first_conn.close()
        second_conn.close()


def test_finished_job_allows_publishing_again(client, group_with_post):
    """Ограничение — только на активные задачи: переопубликовать пост можно."""
    pid = make_post(client, group_with_post)
    path = f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish"
    client.post(path, headers=auth(group_with_post["token"]))
    drain_publish_queue()
    client.post(path, headers=auth(group_with_post["token"]))
    assert len(jobs_for(pid)) == 2


# ── Ошибки ───────────────────────────────────────────────────────────────────

def test_failure_is_recorded_on_the_job(client, group_with_post, monkeypatch):
    pid = make_post(client, group_with_post)
    monkeypatch.setattr(publish_queue, "perform_publish",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ВК лёг")))
    client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    )
    drain_publish_queue()
    job = jobs_for(pid)[-1]
    assert job["state"] == "failed"
    assert "ВК лёг" in job["error"]


def test_social_error_is_visible_but_job_completes(client, group_with_post, monkeypatch):
    """
    Отказ соцсети — не провал очереди. Задача считается выполненной, но причина
    должна быть видна: иначе человек не поймёт, почему поста нет в паблике.
    """
    pid = make_post(client, group_with_post)
    monkeypatch.setattr(publish_queue, "perform_publish",
                        lambda *a, **kw: {"tg_error": "чат не найден"})
    client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    )
    drain_publish_queue()
    job = jobs_for(pid)[-1]
    assert job["state"] == "done"
    assert "чат не найден" in job["error"]


def test_deleted_post_fails_gracefully(client, group_with_post):
    pid = make_post(client, group_with_post)
    conn = get_db()
    publish_queue.enqueue(conn, pid, group_with_post["group_id"], None)
    conn.close()
    client.delete(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}",
        headers=auth(group_with_post["token"]),
    )
    assert drain_publish_queue() == 0, "задача уходит вместе с постом"


def test_interrupted_jobs_are_flagged_not_retried(client, group_with_post):
    """
    После падения процесса неизвестно, успел ли пост уйти. Повторять нельзя:
    лишняя запись на стене хуже неопубликованной.
    """
    pid = make_post(client, group_with_post)
    conn = get_db()
    publish_queue.enqueue(conn, pid, group_with_post["group_id"], None)
    conn.close()
    conn = get_db()
    publish_queue.claim_job(conn)  # взяли в работу и «упали»
    conn.close()

    assert publish_queue.requeue_stuck_jobs() >= 1
    job = jobs_for(pid)[-1]
    assert job["state"] == "failed"
    assert "прервалась" in job["error"]
    assert drain_publish_queue() == 0


# ── Как это видно снаружи ────────────────────────────────────────────────────

def test_job_state_is_readable_by_the_author(client, group_with_post):
    pid = make_post(client, group_with_post)
    job = client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    ).json()
    r = client.get(f"/api/publish-jobs/{job['id']}", headers=auth(group_with_post["token"]))
    assert r.status_code == 200
    assert r.json()["state"] in ("queued", "running", "done")


def test_job_state_is_hidden_from_strangers(client, group_with_post, make_user):
    pid = make_post(client, group_with_post)
    job = client.post(
        f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
        headers=auth(group_with_post["token"]),
    ).json()
    stranger, _ = make_user("nosy")
    assert client.get(f"/api/publish-jobs/{job['id']}", headers=auth(stranger)).status_code == 403


def test_post_reports_its_last_job(client, group_with_post):
    """Интерфейс восстанавливает состояние после перезагрузки страницы."""
    pid = make_post(client, group_with_post)
    token = auth(group_with_post["token"])
    assert client.get(f"/api/posts/{pid}/publish-job", headers=token).json()["state"] == "none"

    client.post(f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish", headers=token)
    assert client.get(f"/api/posts/{pid}/publish-job", headers=token).json()["state"] == "queued"
    drain_publish_queue()
    assert client.get(f"/api/posts/{pid}/publish-job", headers=token).json()["state"] == "done"


@pytest.mark.parametrize("path", ["/api/publish-jobs/999999", "/api/posts/999999/publish-job"])
def test_unknown_job_is_404(client, admin_token, path):
    assert client.get(path, headers=auth(admin_token)).status_code == 404


def test_batch_is_capped(client, group_with_post):
    """Один заход воркера не должен разгребать очередь бесконечно."""
    for i in range(4):
        pid = make_post(client, group_with_post, f"Пачка {i}")
        client.post(
            f"/api/groups/{group_with_post['group_id']}/posts/{pid}/publish",
            headers=auth(group_with_post["token"]),
        )
    assert publish_queue.process_jobs(max_jobs=2) == 2
