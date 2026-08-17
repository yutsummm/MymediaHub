"""
Очередь публикации.

Публикация шла прямо внутри HTTP-запроса. Загрузка видео в ВК идёт с таймаутом
120 секунд на файл, а файлов в посте может быть несколько — тяжёлый пост либо
подвешивал запрос, либо отваливался по таймауту прокси. Причём отвалившийся
запрос ничего не отменял: пост к тому моменту мог уже уйти в паблик, а человек
видел ошибку и жал «Опубликовать» ещё раз.

Теперь ручка публикации только ставит задачу в очередь и сразу отвечает, а
отправкой занимается фоновый воркер. Интерфейс следит за состоянием задачи.

Состояния: queued → running → done | failed.
"""
import json

from logs import get_logger
from publishing import perform_publish
from utils import app_now, get_db

# Один пост не может стоять в очереди дважды — это гарантирует частичный
# уникальный индекс uq_publish_jobs_active. Два клика по «Опубликовать» не
# должны дать две записи на стене.
ACTIVE_STATES = ("queued", "running")

log = get_logger("publish")


def enqueue(conn, post_id: int, group_id: int | None, user_id: int | None) -> dict:
    """
    Ставит пост в очередь. Если он уже там — возвращает существующую задачу,
    а не заводит вторую.
    """
    c = conn.cursor()
    c.execute(
        "SELECT * FROM publish_jobs WHERE post_id=%s AND state = ANY(%s) "
        "ORDER BY id DESC LIMIT 1",
        (post_id, list(ACTIVE_STATES)),
    )
    existing = c.fetchone()
    if existing:
        return dict(existing)

    c.execute(
        "INSERT INTO publish_jobs (post_id, group_id, requested_by, state, created_at) "
        "VALUES (%(post_id)s, %(group_id)s, %(requested_by)s, 'queued', %(created_at)s) "
        "RETURNING *",
        {"post_id": post_id, "group_id": group_id, "requested_by": user_id,
         "created_at": app_now()},
    )
    job = dict(c.fetchone())
    conn.commit()
    return job


def get_job(conn, job_id: int) -> dict | None:
    c = conn.cursor()
    c.execute("SELECT * FROM publish_jobs WHERE id=%s", (job_id,))
    row = c.fetchone()
    return dict(row) if row else None


def job_for_post(conn, post_id: int) -> dict | None:
    """Последняя задача по посту — по ней интерфейс показывает состояние."""
    c = conn.cursor()
    c.execute("SELECT * FROM publish_jobs WHERE post_id=%s ORDER BY id DESC LIMIT 1", (post_id,))
    row = c.fetchone()
    return dict(row) if row else None


def claim_job(conn):
    """
    Забирает одну задачу в работу.

    SKIP LOCKED и смена состояния в одном запросе: две копии воркера не должны
    взять одну задачу — отозвать публикацию из ВК и Telegram нельзя.
    """
    c = conn.cursor()
    c.execute(
        "UPDATE publish_jobs SET state='running', attempts = attempts + 1 "
        "WHERE id = ("
        "  SELECT id FROM publish_jobs WHERE state='queued' "
        "  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
        ") RETURNING *",
    )
    job = c.fetchone()
    conn.commit()
    return dict(job) if job else None


def _finish(conn, job_id: int, state: str, error: str | None, result: dict | None) -> None:
    c = conn.cursor()
    c.execute(
        "UPDATE publish_jobs SET state=%(state)s, error=%(error)s, result=%(result)s, "
        "finished_at=%(finished_at)s WHERE id=%(id)s",
        {"state": state, "error": error,
         "result": json.dumps(result, ensure_ascii=False) if result else None,
         "finished_at": app_now(), "id": job_id},
    )
    conn.commit()


def run_job(conn, job: dict) -> bool:
    """Выполняет одну задачу. True — опубликовано."""
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id=%s", (job["post_id"],))
    post = c.fetchone()
    if not post:
        _finish(conn, job["id"], "failed", "Пост удалён до публикации", None)
        return False

    try:
        result = perform_publish(conn, post, group_id=job.get("group_id"))
    except Exception as e:
        # Повторять нельзя: публикация не идемпотентна, и повтор после таймаута
        # легко даст вторую запись на стене. Ошибку сохраняем, человек решает сам.
        conn.rollback()
        _finish(conn, job["id"], "failed", str(e), None)
        log.error(f"❌  задача публикации #{job['id']}: {e}")
        return False

    # Соцсеть могла отказать, хотя сама задача отработала — это не провал
    # очереди, но человек должен видеть, что именно не ушло.
    problems = [str(result.get(k)) for k in ("vk_error", "tg_error") if result.get(k)]
    _finish(
        conn, job["id"], "done", "; ".join(problems) or None,
        {k: result.get(k) for k in
         ("vk_post_id", "vk_error", "vk_photo_errors", "tg_message_ids", "tg_error")},
    )
    return True


def process_jobs(max_jobs: int = 5) -> int:
    """Разбирает очередь. Возвращает количество обработанных задач."""
    done = 0
    conn = get_db()
    try:
        while done < max_jobs:
            job = claim_job(conn)
            if not job:
                break
            done += 1
            try:
                run_job(conn, job)
            except Exception:
                log.exception(f"задача публикации #{job['id']} упала")
    finally:
        conn.close()
    return done


def requeue_stuck_jobs() -> int:
    """
    Задачи, застрявшие в running после падения процесса.

    В очередь их не возвращаем: неизвестно, успел ли пост уйти в паблик до
    падения, а лишняя запись на стене хуже неопубликованной. Помечаем как
    неудачные с внятной причиной — решение за человеком.
    """
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            "UPDATE publish_jobs SET state='failed', error=%s, finished_at=%s "
            "WHERE state='running' RETURNING id",
            ("Публикация прервалась на полпути. Проверьте паблик: пост мог уйти. "
             "Автоматически она не повторится, чтобы не опубликовать дважды.",
             app_now()),
        )
        stuck = c.fetchall()
        conn.commit()
    finally:
        conn.close()
    if stuck:
        log.warning(f"⚠️   прерванных задач публикации: {len(stuck)} ({[r['id'] for r in stuck]})")
    return len(stuck)
