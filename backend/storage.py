"""
Уборка загруженных файлов: удаляем то, на что больше никто не ссылается.

Файлы не стирались никогда — во всём приложении не было ни одного места, где
файл удаляется с диска. Строка из базы уходила, файл оставался; отклонённые
материалы, то есть заведомо ненужные, лежали наравне с одобренными. Хранилище
только росло, а разгребать его пришлось бы руками и вслепую: после удаления
строки связь «файл — чья загрузка» уже утеряна.

**Почему обход, а не удаление в каждом месте, где что-то стирается.** Файл
осиротеть может шестью разными путями, и один из них приложению недоступен
вовсе: удаление группы уносит её посты каскадом в самой базе, и дописать туда
вызов уборки нечего. Поштучная уборка полной быть не может в принципе, а
обход находит осиротевшее независимо от того, как оно осиротело. Одно место,
знающее правду, вместо шести мест, о которых надо помнить.

**Отсрочка обязательна.** Между загрузкой файла и сохранением поста проходит
время — человек пишет текст, отвлекается, возвращается. Всё это время файл на
диске уже есть, а ссылки на него ещё нет нигде. Обход без отсрочки удалял бы
картинки прямо из-под редактора.

**Предохранитель.** Пустой список ссылок означает либо «в системе нет ни
одного медиафайла», либо ошибку в запросе. Второе неотличимо от первого по
результату, но последствия разные: во втором случае обход сотрёт всё
хранилище, и это необратимо. Поэтому при пустом списке ссылок и непустых
таблицах обход отказывается работать.
"""
import os
import re
import time

from logs import get_logger
from utils import UPLOAD_DIR, upload_filename

log = get_logger("storage")

# Имена, которые выдаёт загрузка: случайный идентификатор плюс расширение.
# **Обход ходит только по ним, а не по всему, что лежит в каталоге.** Общей
# проверки имени тут мало: под неё подходит и `.gitkeep`, и любой файл, который
# положил туда человек, — а уборка не должна распоряжаться чужим.
OWN_FILE_RE = re.compile(r"^[0-9a-f]{32}\.[^.]{1,16}$")

# Сколько файл живёт неприкосновенным после загрузки. Сутки — с запасом на то,
# что человек начал пост вечером, а дописал утром.
GRACE_SECONDS = int(os.getenv("UPLOAD_GRACE_HOURS", "24")) * 3600
# Через сколько дней отклонённая загрузка удаляется вместе с файлами.
REJECTED_KEEP_DAYS = int(os.getenv("REJECTED_KEEP_DAYS", "30"))


def referenced_urls(conn) -> set[str]:
    """Все ссылки на файлы, на которые кто-то ссылается сейчас."""
    c = conn.cursor()
    c.execute(
        """
        SELECT DISTINCT m->>'url' AS url
          FROM posts, LATERAL jsonb_array_elements(media) AS m
         WHERE jsonb_typeof(media) = 'array'
        UNION
        SELECT DISTINCT m->>'url' AS url
          FROM volunteer_media, LATERAL jsonb_array_elements(media) AS m
         WHERE jsonb_typeof(media) = 'array'
        """
    )
    return {row["url"] for row in c.fetchall() if row["url"]}


def _rows_with_media(conn) -> int:
    """Сколько записей вообще держат медиа. Нужно предохранителю."""
    c = conn.cursor()
    c.execute(
        "SELECT (SELECT COUNT(*) FROM posts WHERE jsonb_typeof(media)='array' "
        "          AND jsonb_array_length(media) > 0) "
        "     + (SELECT COUNT(*) FROM volunteer_media WHERE jsonb_typeof(media)='array' "
        "          AND jsonb_array_length(media) > 0) AS n"
    )
    row = c.fetchone()
    return (row["n"] if row else 0) or 0


def purge_rejected(conn, days: int = REJECTED_KEEP_DAYS) -> int:
    """
    Удаляет отклонённые загрузки старше срока.

    Сами файлы уберёт обход — здесь только строки: пока строка жива, файл
    считается нужным, и это правильно. Одобренные и ожидающие не трогаем
    никогда: у первых материал в работе, вторые ещё никто не смотрел.
    """
    c = conn.cursor()
    c.execute(
        "DELETE FROM volunteer_media "
        " WHERE status='rejected' AND created_at < NOW() - make_interval(days => %s)",
        (days,),
    )
    removed = c.rowcount or 0
    conn.commit()
    return removed


def sweep(conn, grace_seconds: int = GRACE_SECONDS) -> dict:
    """
    Удаляет файлы, на которые никто не ссылается и которые старше отсрочки.

    Возвращает сводку: сколько удалено, сколько байт освобождено, сколько
    файлов пощадила отсрочка.
    """
    if not os.path.isdir(UPLOAD_DIR):
        return {"deleted": 0, "freed_bytes": 0, "too_young": 0, "kept": 0}

    used = referenced_urls(conn)
    if not used and _rows_with_media(conn) > 0:
        # Предохранитель: ссылок нет, а записи с медиа есть — это не пустая
        # система, это сломанный запрос. Удалять в такой ситуации нельзя.
        log.error("уборка отменена: ссылок не нашлось, хотя записи с медиа есть")
        return {"deleted": 0, "freed_bytes": 0, "too_young": 0, "kept": 0,
                "aborted": True}

    used_names = {upload_filename(url) for url in used}
    now = time.time()
    deleted = freed = too_young = kept = 0

    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if not OWN_FILE_RE.match(name) or not os.path.isfile(path):
            continue
        if name in used_names:
            kept += 1
            continue
        try:
            stat = os.stat(path)
            if now - stat.st_mtime < grace_seconds:
                too_young += 1
                continue
            os.remove(path)
        except OSError as e:
            log.warning(f"не удалось убрать {name}: {type(e).__name__}: {e}")
            continue
        deleted += 1
        freed += stat.st_size

    if deleted:
        log.info(f"🧹  убрано файлов: {deleted}, освобождено {freed // 1024} КБ")
    return {"deleted": deleted, "freed_bytes": freed,
            "too_young": too_young, "kept": kept}


def run() -> dict:
    """Такт уборки: сначала строки отклонённых, потом осиротевшие файлы."""
    from utils import get_db

    conn = get_db()
    try:
        rejected = purge_rejected(conn)
        if rejected:
            log.info(f"🗑️   удалено отклонённых загрузок: {rejected}")
        result = sweep(conn)
        result["rejected_rows"] = rejected
        return result
    finally:
        conn.close()
