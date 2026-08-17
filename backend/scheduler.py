"""
Автопубликация отложенных постов.

Планировщика в проекте не было вовсе: статус `scheduled` и поле `scheduled_at`
существовали, календарь позволял двигать посты по датам, но публиковать их в
назначенное время было некому — на проде висели посты, просроченные на месяцы.

Отдельный воркер или cron-сервис для одного запроса раз в минуту избыточны:
сервис и так однопоточный (том Railway не даёт больше одного инстанса, миграции
крутятся в startup). Поэтому — фоновая задача внутри приложения.
"""
import asyncio
import os
from datetime import timedelta

from health import beat
from logs import get_logger
from publish_queue import enqueue, process_jobs, requeue_stuck_jobs
from telegram_stats import (
    TELEGRAM_POLL_INTERVAL,
    TELEGRAM_STATS_ENABLED,
    collect_telegram_stats,
)
from utils import app_now, get_db

SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "1").strip().lower() not in ("0", "false", "no")
SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60"))
# Предохранитель от бесконечного цикла, если публикация почему-то не снимает
# пост с очереди: за один заход берём ограниченную пачку.
MAX_PER_TICK = int(os.getenv("SCHEDULER_MAX_PER_TICK", "10"))
# Насколько просроченный пост ещё имеет смысл публиковать. Планировщик может
# простоять (выкатка, падение, как здесь — его вообще не было три месяца), и
# анонс мероприятия, которое прошло в мае, выкидывать в живой паблик нельзя.
# Всё, что старше, помечается пропущенным и ждёт решения человека.
MAX_DELAY_MINUTES = int(os.getenv("SCHEDULER_MAX_DELAY_MINUTES", "120"))
# Очередь публикации разбирается чаще: человек нажал «Опубликовать» и ждёт.
PUBLISH_POLL_INTERVAL = int(os.getenv("PUBLISH_POLL_SECONDS", "3"))

log = get_logger("scheduler")


def _window() -> tuple[object, object]:
    """Границы «созревших, но ещё не протухших»: (не раньше, не позже)."""
    now = app_now()
    return now - timedelta(minutes=MAX_DELAY_MINUTES), now


def claim_due_post(conn):
    """
    Атомарно забирает один созревший пост.

    Заявкой служит publish_attempts: берём только посты с нулём попыток и тут же
    увеличиваем счётчик. Одной блокировки строки не хватает — она снимается на
    коммите, а статус до самой публикации остаётся 'scheduled', и тот же пост
    достался бы второму обработчику. Отозвать публикацию из ВК и Telegram
    нельзя, поэтому дубль недопустим.

    Обратная сторона: если процесс умрёт между заявкой и публикацией, пост
    останется невыпущенным навсегда. Это осознанный размен — молча
    опубликовать дважды хуже, чем не опубликовать. Такие посты подсвечивает
    flag_interrupted_posts() при старте.
    """
    earliest, now = _window()
    c = conn.cursor()
    c.execute(
        "UPDATE posts SET publish_attempts = publish_attempts + 1 "
        "WHERE id = ("
        "  SELECT id FROM posts "
        "  WHERE status='scheduled' AND publish_attempts = 0 "
        "        AND scheduled_at IS NOT NULL "
        "        AND scheduled_at <= %s AND scheduled_at >= %s "
        "  ORDER BY scheduled_at "
        "  FOR UPDATE SKIP LOCKED "
        "  LIMIT 1"
        ") RETURNING *",
        (now, earliest),
    )
    post = c.fetchone()
    conn.commit()
    return post


def flag_missed_posts() -> int:
    """
    Помечает посты, срок которых прошёл слишком давно.

    Публиковать их автоматически нельзя: планировщика в проекте не было вовсе,
    и в очереди копились анонсы мероприятий, которые давно прошли. Выкинуть их
    разом в живой паблик при первом же запуске — худшее, что можно сделать.
    """
    earliest, _ = _window()
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE posts SET publish_error=%s "
        "WHERE status='scheduled' AND scheduled_at IS NOT NULL "
        "      AND scheduled_at < %s AND publish_error IS NULL "
        "RETURNING id",
        (f"Срок публикации пропущен больше чем на {MAX_DELAY_MINUTES} мин. "
         "Автоматически пост не уйдёт — проверьте, актуален ли он, и "
         "опубликуйте вручную или назначьте новую дату.", earliest),
    )
    missed = c.fetchall()
    conn.commit()
    conn.close()
    if missed:
        log.warning(f"⚠️   пропущенных отложенных постов: {len(missed)} ({[r['id'] for r in missed]})")
    return len(missed)


def flag_interrupted_posts() -> int:
    """
    Помечает посты, оборвавшиеся на полпути: заявка есть, публикации не было.

    Такое остаётся после падения или рестарта в момент отправки. Сами мы их не
    трогаем (см. claim_due_post), но человек должен видеть, что пост завис, а не
    гадать, почему он не вышел.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE posts SET publish_error=%s "
        "WHERE status='scheduled' AND publish_attempts > 0 AND publish_error IS NULL "
        "RETURNING id",
        ("Публикация прервалась на полпути. Отправьте пост вручную — "
         "автоматически он повторно не уйдёт, чтобы не опубликоваться дважды.",),
    )
    stuck = c.fetchall()
    conn.commit()
    conn.close()
    if stuck:
        log.warning(f"⚠️   зависших отложенных постов: {len(stuck)} ({[r['id'] for r in stuck]})")
    return len(stuck)


def publish_due_posts() -> int:
    """Публикует все созревшие посты. Возвращает, сколько отправлено."""
    published = 0
    flag_missed_posts()
    conn = get_db()
    try:
        while published < MAX_PER_TICK:
            post = claim_due_post(conn)
            if not post:
                break
            published += 1
            try:
                # Отправкой занимается воркер очереди — тот же путь, что и у
                # ручной публикации. Иначе тяжёлое видео вешало бы такт
                # планировщика на минуты.
                enqueue(conn, post["id"], post.get("group_id"), post.get("author_id"))
                log.info(f"⏰  отложенный пост #{post['id']} поставлен в очередь")
            except Exception as e:
                # Сеть, соцсеть, что угодно. Пост уже снят с очереди: повторять
                # автоматически нельзя — публикация не идемпотентна, и повтор
                # после таймаута легко даст вторую запись на стене.
                conn.rollback()
                c = conn.cursor()
                c.execute(
                    "UPDATE posts SET publish_error=%s WHERE id=%s",
                    (f"Автопубликация не удалась: {e}", post["id"]),
                )
                c.execute(
                    "INSERT INTO notifications (user_id, message, type, is_read) "
                    "VALUES (%s, %s, %s, 0)",
                    (post.get("author_id") or 1,
                     f"Не удалось опубликовать отложенный пост «{post.get('title')}»: {e}",
                     "error"),
                )
                conn.commit()
                log.error(f"❌  отложенный пост #{post['id']}: {e}")
    finally:
        conn.close()
    return published


async def _run_loop(name: str, work, interval: int):
    """
    Общий каркас фонового такта: отработать, отметить пульс, поспать.

    Цикл не имеет права умереть: иначе отложенные посты снова перестанут
    выходить, а снаружи это будет незаметно. Отсюда же и пульс — единственный
    способ узнать, что цикл жив, не глядя на его последствия. Отмечается он
    только после успешного такта: цикл, который каждый раз падает, обязан
    выглядеть мёртвым, а не бодрым.
    """
    while True:
        try:
            await asyncio.to_thread(work)
            beat(name)
        except Exception:
            log.exception(f"такт «{name}» упал, цикл продолжается")
        await asyncio.sleep(interval)


async def scheduler_loop():
    await _run_loop("scheduler", publish_due_posts, SCHEDULER_INTERVAL)


async def publish_worker_loop():
    """
    Разбирает очередь публикации.

    Отдельный цикл, а не общий с планировщиком: один тяжёлый пост с видео
    занимает минуты, и такт «кому пора выходить» не должен его ждать.
    """
    await _run_loop("publish_worker", process_jobs, PUBLISH_POLL_INTERVAL)


async def telegram_stats_loop():
    """
    Отдельный такт: реакции Telegram нельзя запросить задним числом, их надо
    вычитывать из потока апдейтов. Но делать это каждую минуту незачем — у
    Telegram апдейты живут около суток.
    """
    await _run_loop("telegram_stats", collect_telegram_stats, TELEGRAM_POLL_INTERVAL)


def start(app) -> None:
    if not SCHEDULER_ENABLED:
        log.info("⏰  планировщик отключён (SCHEDULER_ENABLED=0)")
        return
    for sweep in (flag_interrupted_posts, requeue_stuck_jobs):
        try:
            sweep()
        except Exception:
            log.exception(f"стартовая уборка {sweep.__name__} не отработала")
    app.state.scheduler_task = asyncio.create_task(scheduler_loop())
    app.state.publish_worker_task = asyncio.create_task(publish_worker_loop())
    log.info(f"📮  воркер публикации запущен, очередь раз в {PUBLISH_POLL_INTERVAL} с")
    log.info(f"⏰  планировщик запущен, проверка каждые {SCHEDULER_INTERVAL} с")
    if TELEGRAM_STATS_ENABLED:
        app.state.telegram_stats_task = asyncio.create_task(telegram_stats_loop())
        log.info(f"📊  сбор реакций Telegram запущен, раз в {TELEGRAM_POLL_INTERVAL} с")
