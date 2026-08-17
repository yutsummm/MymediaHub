"""
Проверка состояния для мониторинга.

Логи отвечают на вопрос «что случилось», но только когда уже случилось и когда
кто-то в них смотрит. Второй половины наблюдаемости не было вовсе: узнать
снаружи, жив ли планировщик, не давал ни один способ — а он ровно тот механизм,
чью смерть по интерфейсу не видно. Отложенные посты просто перестают выходить,
и замечают это через сутки.

`GET /api/health` отвечает 200, когда всё в порядке, и 503, когда нет — этого
достаточно любому аптайм-чекеру. Внутри: доступность базы, свежесть схемы,
пульс фоновых циклов, длина очереди публикации и число просроченных постов.

Ручка открыта без авторизации сознательно: мониторинг ходит без токена. Наружу
уходят только флаги и счётчики — ни настроек, ни данных пользователей.
"""
import time
from datetime import datetime

from logs import get_logger
from utils import app_now, get_db

log = get_logger("health")

STARTED_AT = time.monotonic()

# Пульс фоновых циклов: имя такта → когда он последний раз отработал.
# Живёт в памяти процесса, и это правильно: вопрос «жив ли мой цикл» —
# про этот конкретный процесс, а не про систему в целом.
HEARTBEATS: dict[str, datetime] = {}

# Во сколько раз такт может опоздать, прежде чем считать цикл мёртвым.
STALE_FACTOR = 3


def beat(name: str) -> None:
    HEARTBEATS[name] = app_now()


def _age_seconds(name: str) -> float | None:
    last = HEARTBEATS.get(name)
    return None if last is None else (app_now() - last).total_seconds()


def _database() -> dict:
    started = time.monotonic()
    conn = get_db()
    try:
        conn.cursor().execute("SELECT 1")
    finally:
        conn.close()
    return {"ok": True, "latency_ms": round((time.monotonic() - started) * 1000, 1)}


def _queue(conn) -> dict:
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FILTER (WHERE state='queued') AS queued, "
        "       COUNT(*) FILTER (WHERE state='running') AS running, "
        "       COUNT(*) FILTER (WHERE state='failed' "
        "                        AND created_at > NOW() - INTERVAL '24 hours') AS failed_24h "
        "FROM publish_jobs"
    )
    return dict(c.fetchone())


def _overdue_posts(conn) -> int:
    """
    Посты, которым пора было выйти, но они всё ещё ждут. Больше нуля —
    планировщик либо стоит, либо не справляется.
    """
    import scheduler

    c = conn.cursor()
    # secs, а не mins: у make_interval параметр `mins` объявлен как integer, а
    # деление в Python даёт float — запрос падал с «function make_interval(mins
    # => numeric) does not exist» при любом значении такта. Ошибку глотал
    # обработчик выше, и счётчик просроченных постов не считался никогда, то
    # есть единственный внешний признак вставшего планировщика молчал.
    # У `secs` тип double precision, дробное значение он принимает как есть.
    c.execute(
        "SELECT COUNT(*) AS n FROM posts WHERE status='scheduled' AND scheduled_at IS NOT NULL "
        "AND scheduled_at < NOW() - make_interval(secs => %s)",
        (scheduler.SCHEDULER_INTERVAL * 3,),
    )
    return c.fetchone()["n"]


def _loops() -> dict:
    """Сверяет пульс каждого цикла с его собственным тактом."""
    import scheduler

    if not scheduler.SCHEDULER_ENABLED:
        return {"enabled": False}

    expected = {
        "scheduler": scheduler.SCHEDULER_INTERVAL,
        "publish_worker": scheduler.PUBLISH_POLL_INTERVAL,
    }
    if scheduler.TELEGRAM_STATS_ENABLED:
        expected["telegram_stats"] = scheduler.TELEGRAM_POLL_INTERVAL

    loops: dict = {"enabled": True}
    for name, interval in expected.items():
        age = _age_seconds(name)
        loops[name] = {
            "last_run_seconds_ago": None if age is None else round(age),
            # Пульса нет вовсе — цикл ещё не успел отработать первый такт;
            # это не повод бить тревогу сразу после старта.
            "ok": age is None or age <= interval * STALE_FACTOR,
        }
    return loops


def collect() -> tuple[dict, bool]:
    """Собирает состояние. Возвращает (отчёт, всё ли в порядке)."""
    report: dict = {"uptime_seconds": round(time.monotonic() - STARTED_AT)}
    healthy = True

    try:
        report["database"] = _database()
    except Exception as e:
        log.exception("health: база недоступна")
        report["database"] = {"ok": False, "error": str(e)}
        # Без базы остальное не проверить, а само по себе это уже отказ.
        return report, False

    from main import schema_is_current

    try:
        schema_ok, message = schema_is_current()
        report["schema"] = {"ok": schema_ok, "message": message}
        healthy = healthy and schema_ok
    except Exception as e:
        report["schema"] = {"ok": False, "message": str(e)}
        healthy = False

    conn = get_db()
    try:
        # Две проверки — два обработчика: раньше они делили один, и поломка
        # счётчика просроченных постов приходила наружу как ошибка очереди
        # публикации, хотя с очередью всё было в порядке.
        try:
            report["publish_queue"] = _queue(conn)
        except Exception as e:
            log.exception("health: не удалось снять состояние очереди")
            report["publish_queue"] = {"error": str(e)}
        try:
            report["overdue_posts"] = _overdue_posts(conn)
        except Exception as e:
            log.exception("health: не удалось посчитать просроченные посты")
            report["overdue_posts"] = {"error": str(e)}
    finally:
        conn.close()

    report["loops"] = _loops()
    if report["loops"].get("enabled"):
        healthy = healthy and all(
            v["ok"] for v in report["loops"].values() if isinstance(v, dict)
        )

    report["status"] = "ok" if healthy else "degraded"
    return report, healthy
