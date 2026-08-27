"""
MediaHub — shared utilities and helpers
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from math import asin, cos, radians, sin, sqrt

import bcrypt
import psycopg2
import psycopg2.extras
import requests as http_requests
from fastapi import Header, HTTPException, Request
from jose import JWTError, jwt
from psycopg2.extras import Json

import richtext
from logs import get_logger, user_id_var

# ── DB ───────────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mediahub:mediahub123@localhost:5432/mediahub")

def _session_options() -> str:
    """
    Параметры сессии Postgres: часовой пояс — APP_TZ.

    От зоны сессии зависят все выражения вида `published_at::date`: без явной
    установки Postgres берёт зону сервера (на Railway это UTC), и «день» в
    аналитике заканчивался бы в 17:00 по Красноярску. Раньше это было незаметно
    ровно потому, что читалось как «просто сдвинутый график».

    Зона уходит вместе с параметрами подключения — лишнего запроса нет.
    Незнакомое значение APP_TZ не должно ронять подключение: `app_now()` в этом
    случае тоже не падает, а предупреждает и работает по часам контейнера.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(APP_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ""
    return f"-c timezone={APP_TZ}"


def get_db():
    opts = _session_options()
    kwargs = {"options": opts} if opts else {}
    return psycopg2.connect(
        DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor, **kwargs
    )


def like_pattern(query: str) -> str:
    """
    Строка поиска → шаблон для ILIKE.

    Спецсимволы LIKE экранируются: без этого «50%» искалось как «50 и что
    угодно», а одиночный «%» совпадал вообще со всем. Экранирующий символ —
    обратный слэш, он же по умолчанию у LIKE в Postgres, поэтому ESCAPE
    в запросе указывать не нужно.
    """
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


JSON_FIELDS = ("platforms", "tags", "media", "tg_message_ids")
# Поля, которые наружу отдаются строкой «YYYY-MM-DDTHH:MM»: в базе они
# timestamptz, но интерфейс ждёт прежний формат.
DATE_FIELDS = (
    "created_at", "scheduled_at", "published_at", "vk_stats_updated_at",
    "joined_at", "connected_at", "updated_at", "finished_at",
    "submitted_at", "reviewed_at", "auto_delete_at", "removed_at",
)


def as_json_list(value) -> list:
    """
    Значение JSON-колонки списком.

    Колонки теперь jsonb, и psycopg2 отдаёт готовые list/dict. Разбор строки
    оставлен для значений, записанных до перевода типа, и для случая, когда
    в колонке оказалось не то, что ожидали.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    for key in JSON_FIELDS:
        d[key] = as_json_list(d.get(key))
    for key in DATE_FIELDS:
        if key in d:
            d[key] = fmt_dt(d[key])
    # Ссылки на файлы уходят наружу подписанными: /uploads отдаёт только по
    # действующей подписи. Через row_to_dict проходят все посты, поэтому одна
    # точка закрывает их целиком.
    if "media" in d:
        d["media"] = sign_media_list(d["media"])
    return d


# ── Время приложения ─────────────────────────────────────────────────────────
# Даты в базе — текст «YYYY-MM-DDTHH:MM» без зоны, и пишут их два разных
# источника: scheduled_at приходит из браузера (местное время Красноярска),
# а контейнер и Postgres на Railway живут в UTC. Сравнивать одно с другим
# напрямую нельзя — отложенный пост уехал бы на 7 часов.
# Поэтому «сейчас» у приложения всегда в APP_TZ.

APP_TZ = os.getenv("APP_TZ", "Asia/Krasnoyarsk")

log = get_logger("utils")


def app_now() -> datetime:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return datetime.now(ZoneInfo(APP_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        log.warning(f"неизвестная таймзона APP_TZ={APP_TZ!r}, беру время контейнера")
        return datetime.now()


DATE_FORMAT = "%Y-%m-%dT%H:%M"


def app_now_str() -> str:
    """«Сейчас» в том формате, в котором даты уходят наружу."""
    return app_now().strftime(DATE_FORMAT)


def fmt_dt(value) -> str | None:
    """
    Дата наружу: «YYYY-MM-DDTHH:MM» в зоне приложения.

    В базе теперь timestamptz, но договор с интерфейсом не меняем — формат
    хранения и формат выдачи это разные вещи.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value[:16]
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        local = value.astimezone(ZoneInfo(APP_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        local = value
    return local.strftime(DATE_FORMAT)


def parse_dt(value):
    """
    Дата из запроса. Приходит без зоны («2026-08-16T18:00») и означает местное
    время — именно его человек видит в браузере.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return value
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(APP_TZ))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return parsed


# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == hashed


# ── JWT helpers ──────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET") or ""
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    log.warning(
        "JWT_SECRET не задан — взят случайный ключ. После перезапуска все токены "
        "перестанут работать, а секреты интеграций (ключ выводится из JWT_SECRET) "
        "станут нечитаемыми. Задайте JWT_SECRET в окружении."
    )
JWT_ALGORITHM = "HS256"


TOKEN_TTL = timedelta(hours=int(os.getenv("TOKEN_TTL_HOURS", "72")))
# Отметку «был активен» пишем не на каждом запросе: это запись в базу на каждое
# обращение ради поля, которое никто не читает чаще раза в минуту.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


def create_token(user_id: int, request=None, conn=None) -> str:
    """
    Выдаёт токен и заводит под него сессию.

    Без сессии токен нельзя было отозвать ничем: выход существовал только на
    клиенте, а сам токен оставался действительным до 72 часов.
    """
    jti = secrets.token_urlsafe(24)
    expire = datetime.now(UTC) + TOKEN_TTL
    own_conn = conn is None
    conn = conn or get_db()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO sessions (jti, user_id, expires_at, ip, user_agent) "
            "VALUES (%(jti)s, %(user_id)s, %(expires_at)s, %(ip)s, %(user_agent)s)",
            {
                "jti": jti,
                "user_id": user_id,
                "expires_at": expire,
                "ip": client_ip(request) if request else None,
                "user_agent": (request.headers.get("user-agent") if request else None) or None,
            },
        )
        conn.commit()
    finally:
        if own_conn:
            conn.close()
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "jti": jti}, JWT_SECRET, algorithm=JWT_ALGORITHM
    )


def revoke_session(jti: str, reason: str, conn=None) -> bool:
    own_conn = conn is None
    conn = conn or get_db()
    try:
        c = conn.cursor()
        c.execute(
            "UPDATE sessions SET revoked_at=NOW(), revoked_reason=%s "
            "WHERE jti=%s AND revoked_at IS NULL RETURNING jti",
            (reason, jti),
        )
        revoked = c.fetchone() is not None
        conn.commit()
    finally:
        if own_conn:
            conn.close()
    return revoked


def revoke_user_sessions(user_id: int, reason: str, conn=None, except_jti: str | None = None) -> int:
    """
    Гасит все токены пользователя.

    Зовётся при смене пароля: раньше сброс пароля не мешал тому, кто уже увёл
    токен, работать с аккаунтом дальше.
    """
    own_conn = conn is None
    conn = conn or get_db()
    try:
        c = conn.cursor()
        c.execute(
            "UPDATE sessions SET revoked_at=NOW(), revoked_reason=%(reason)s "
            "WHERE user_id=%(user_id)s AND revoked_at IS NULL "
            # Одно имя вместо двух одинаковых позиционных значений — раньше
            # except_jti приходилось передавать дважды подряд.
            "  AND (%(except_jti)s::text IS NULL OR jti <> %(except_jti)s) RETURNING jti",
            {"reason": reason, "user_id": user_id, "except_jti": except_jti},
        )
        count = len(c.fetchall())
        conn.commit()
    finally:
        if own_conn:
            conn.close()
    return count


def list_sessions(user_id: int, conn=None) -> list[dict]:
    own_conn = conn is None
    conn = conn or get_db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT jti, created_at, last_seen_at, expires_at, ip, user_agent "
            "FROM sessions WHERE user_id=%s AND revoked_at IS NULL AND expires_at > NOW() "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in c.fetchall()]
    finally:
        if own_conn:
            conn.close()


def purge_sessions() -> int:
    """Просроченные сессии не нужны: подпись всё равно уже недействительна."""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '7 days' RETURNING jti")
        removed = len(c.fetchall())
        conn.commit()
    finally:
        conn.close()
    return removed


def _session_is_active(jti: str) -> tuple[bool, int | None]:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, revoked_at, expires_at, last_seen_at FROM sessions WHERE jti=%s",
            (jti,),
        )
        row = c.fetchone()
        if not row or row["revoked_at"] is not None:
            return False, None
        # Подпись и срок в базе должны сходиться; расходятся — доверяем базе
        if row["expires_at"] <= datetime.now(row["expires_at"].tzinfo):
            return False, None
        last = row["last_seen_at"]
        if last is None or datetime.now(last.tzinfo) - last > SESSION_TOUCH_INTERVAL:
            c.execute("UPDATE sessions SET last_seen_at=NOW() WHERE jti=%s", (jti,))
            conn.commit()
        return True, row["user_id"]
    finally:
        conn.close()


def get_current_user_id(authorization: str = Header(None), request: Request = None) -> int:
    return current_session(authorization, request)[0]


def current_session(
    authorization: str = Header(None), request: Request = None
) -> tuple[int, str | None]:
    """(id пользователя, идентификатор сессии). Второе нужно ручке выхода."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")
    try:
        token = authorization.split(" ", 1)[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError, IndexError):
        raise HTTPException(401, "Недействительный токен")

    jti = payload.get("jti")
    if not jti:
        # Токены, выданные до появления сессий. Отозвать их нельзя, поэтому и
        # принимать не будем: пусть человек войдёт заново.
        raise HTTPException(401, "Сессия устарела, войдите заново")
    active, session_user = _session_is_active(jti)
    if not active or session_user != user_id:
        raise HTTPException(401, "Сессия завершена, войдите заново")
    # Чтобы записи в логе знали, чей это запрос. Ставится здесь, а не в
    # middleware: там токен ещё не разобран.
    #
    # Двумя путями сразу, и оба нужны. Контекстная переменная видна записям,
    # которые сделает сам обработчик. Но синхронные обработчики FastAPI
    # выполняет в отдельном потоке, и обратно в middleware изменение контекста
    # не возвращается — итоговой записи про запрос достаётся request.state.
    user_id_var.set(user_id)
    if request is not None:
        request.state.user_id = user_id
    return user_id, jti


# ── Шифрование секретов в базе ───────────────────────────────────────────────
# Токены соцсетей (vk_settings.access_token, tg_settings.bot_token) — это полный
# доступ к пабликам организации. В открытом виде утечка дампа базы отдаёт их
# целиком. Пишем их шифрованными, читаем через decrypt_secret.

SECRET_PREFIX = "enc:v1:"


def _fernet():
    """
    Ключ берём из TOKEN_ENCRYPTION_KEY, а если его нет — выводим из JWT_SECRET.
    Отдельный ключ лучше, но требовать новую переменную окружения нельзя: на
    уже поднятых окружениях её никто не задаст, и шифрование просто не включится.
    Безопасность при этом не проседает: кто добыл JWT_SECRET, тот и так выпишет
    себе админский токен и прочитает настройки через API.
    """
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    raw = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    if raw:
        return Fernet(raw.encode())
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"mediahub.secrets.v1",
        info=b"social-tokens",
    ).derive(JWT_SECRET.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(value: str | None) -> str | None:
    """Шифрует значение перед записью в базу. None и пустое отдаёт как есть."""
    if not value:
        return value
    if value.startswith(SECRET_PREFIX):
        return value
    return SECRET_PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    """
    Расшифровывает значение из базы. Значения без префикса возвращает как есть:
    в базе остаются строки, записанные до включения шифрования, и ломать на них
    публикацию нельзя — они дошифруются при следующем сохранении настроек.
    """
    if not value or not value.startswith(SECRET_PREFIX):
        return value
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(value[len(SECRET_PREFIX):].encode()).decode()
    except InvalidToken:
        # Сменили JWT_SECRET, не перенеся TOKEN_ENCRYPTION_KEY — расшифровать
        # нечем. Молча отдавать мусор в VK нельзя, лучше внятная ошибка.
        raise HTTPException(
            500,
            "Не удалось расшифровать токен интеграции. Вероятно, сменился "
            "JWT_SECRET или TOKEN_ENCRYPTION_KEY — переподключите интеграцию "
            "в настройках.",
        )


# ── Подписанные ссылки на загрузки ───────────────────────────────────────────
# /uploads раздавался StaticFiles без всякой проверки: кто знает URL, тот качает.
# Медиа закрытых групп были фактически публичны.
#
# Заголовок Authorization к <img src="..."> не приложишь, поэтому доступ даёт
# подпись в самой ссылке: сервер подписывает путь тому, кто уже имеет право
# видеть содержащую запись, и подпись живёт ограниченное время. Ссылка,
# утёкшая наружу, протухает сама.

UPLOAD_URL_TTL = int(os.getenv("UPLOAD_URL_TTL", str(12 * 3600)))
UPLOAD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _upload_key() -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"mediahub.secrets.v1",
        info=b"upload-urls",
    ).derive(JWT_SECRET.encode())


def _upload_signature(filename: str, expires: int) -> str:
    msg = f"{filename}:{expires}".encode()
    return hmac.new(_upload_key(), msg, hashlib.sha256).hexdigest()[:32]


def upload_filename(url: str) -> str:
    """Имя файла из ссылки на загрузку, без подписи и каталогов."""
    return os.path.basename((url or "").split("?", 1)[0])


def strip_upload_signature(url: str | None) -> str | None:
    """
    Убирает подпись перед записью в базу. Фронт присылает медиа обратно ровно в
    том виде, в каком получил, — если не срезать, в базу лягут ссылки с давно
    истёкшей подписью, и та же картинка перестанет открываться.
    """
    if not url or "?" not in url:
        return url
    base = url.split("?", 1)[0]
    return base if base.startswith("/uploads/") else url


def sign_upload_url(url: str | None) -> str | None:
    """Подписывает ссылку на выдачу наружу. Чужие URL не трогает."""
    if not url:
        return url
    base = url.split("?", 1)[0]
    if not base.startswith("/uploads/"):
        return url
    name = os.path.basename(base)
    if not UPLOAD_NAME_RE.match(name):
        return url
    expires = int(time.time()) + UPLOAD_URL_TTL
    return f"/uploads/{name}?exp={expires}&sig={_upload_signature(name, expires)}"


def sign_media_list(media) -> list:
    """Подписывает ссылки во всём списке медиа (посты, материалы волонтёров)."""
    if not isinstance(media, list):
        return media
    signed = []
    for item in media:
        if isinstance(item, dict) and item.get("url"):
            item = {**item, "url": sign_upload_url(item["url"])}
        signed.append(item)
    return signed


def media_for_storage(media) -> Json:
    """
    JSON списка медиа для записи в базу — с вычищенными подписями.
    Единственная точка, через которую медиа должно попадать в posts.media и
    volunteer_media.media.
    """
    items = []
    for item in media or []:
        d = item if isinstance(item, dict) else item.dict()
        if d.get("url"):
            d = {**d, "url": strip_upload_signature(d["url"])}
        items.append(d)
    # Json-обёртка psycopg2: колонка теперь jsonb, а не строка
    return Json(items)


def check_upload_signature(filename: str, expires: str | None, signature: str | None) -> None:
    """Пускает к файлу только по действующей подписи. Иначе — 403/410."""
    if not expires or not signature:
        raise HTTPException(403, "Ссылка на файл должна быть подписана")
    try:
        expires_at = int(expires)
    except ValueError:
        raise HTTPException(403, "Некорректная подпись ссылки")
    if not hmac.compare_digest(_upload_signature(filename, expires_at), signature):
        raise HTTPException(403, "Некорректная подпись ссылки")
    if expires_at < int(time.time()):
        raise HTTPException(410, "Срок действия ссылки на файл истёк")


def decrypt_row_secret(row, field: str) -> dict | None:
    """Строка настроек интеграции с расшифрованным секретом. None пробрасывает."""
    if row is None:
        return None
    d = dict(row)
    d[field] = decrypt_secret(d.get(field))
    return d


# ── Постраничная выдача ──────────────────────────────────────────────────────
# Списки всегда были ограничены limit'ом, но наружу отдавали только текущую
# страницу — а интерфейс её не листал, так что на 101-м посте список молча
# обрывался. Плюс limit ничем не ограничивался сверху: запросом limit=1000000
# можно было заставить сервер вытащить всю таблицу разом.

MAX_PAGE_SIZE = 200


def paging(limit: int, offset: int) -> tuple[int, int]:
    """Приводит limit/offset к разумным границам."""
    return max(1, min(limit, MAX_PAGE_SIZE)), max(0, offset)


def page_meta(total: int, limit: int, offset: int) -> dict:
    """Сведения о странице — по ним интерфейс рисует навигацию."""
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }


# ── Rate limiter ────────────────────────────────────────────────────────────

# Лимиты хранятся в базе, а не в памяти процесса: словарь обнулялся при каждой
# выкатке и ничего не знал о втором инстансе — при двух процессах лимит на
# подбор пароля фактически удваивался. База — единственное, что у сервисов общее.
#
# Окно фиксированное, а не скользящее: при том же смысле («не больше N за
# период») это один запрос вместо чтения и записи списка отметок.

RATE_LIMIT_FALLBACK: dict[str, list[float]] = {}


# 100.64.0.0/10 — shared address space (RFC 6598), в нём живут внутренние прокси
# Railway. Python не относит его к приватным, поэтому перечисляем отдельно:
# без этого «публичным адресом клиента» оказывался бы прокси платформы, а он у
# каждого запроса свой.
_INFRA_NETS = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_infrastructure(addr) -> bool:
    if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
        return True
    return any(addr in net for net in _INFRA_NETS if addr.version == net.version)


def client_ip(request) -> str:
    """
    Адрес клиента с учётом прокси.

    request.client.host на Railway — это адрес их внутреннего прокси, и у
    каждого запроса он свой (100.64.0.3, .5, .6 …). Ключ лимита получался
    каждый раз новым, то есть рейт-лимит на проде не работал вовсе — ни в
    прежнем виде, ни в новом.

    Берём самый правый публичный адрес из X-Forwarded-For: заголовок
    дописывается каждым прокси слева направо, поэтому подставленное клиентом
    значение остаётся левее настоящего и до нас не доходит. Внутренние адреса
    самой платформы пропускаем.
    """
    forwarded = (request.headers.get("x-forwarded-for") or "") if request else ""
    for candidate in reversed([p.strip() for p in forwarded.split(",") if p.strip()]):
        try:
            addr = ipaddress.ip_address(candidate.rsplit(":", 1)[0]
                                        if candidate.count(":") == 1 else candidate)
        except ValueError:
            continue
        if _is_infrastructure(addr):
            continue
        return str(addr)
    if request and request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60):
    try:
        conn = get_db()
    except Exception:
        # База недоступна — не отказываем в обслуживании из-за счётчика.
        # Считаем в памяти: хуже, чем в базе, но лучше, чем ничего.
        return _check_rate_limit_memory(key, max_requests, window_seconds)
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO rate_limits (key, window_start, hits) VALUES (%s, NOW(), 1) "
            "ON CONFLICT (key) DO UPDATE SET "
            "  hits = CASE WHEN rate_limits.window_start < NOW() - make_interval(secs => %s) "
            "              THEN 1 ELSE rate_limits.hits + 1 END, "
            "  window_start = CASE WHEN rate_limits.window_start < NOW() - make_interval(secs => %s) "
            "                      THEN NOW() ELSE rate_limits.window_start END "
            "RETURNING hits",
            (key, window_seconds, window_seconds),
        )
        hits = c.fetchone()["hits"]
        conn.commit()
    finally:
        conn.close()
    if hits > max_requests:
        raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")


def _check_rate_limit_memory(key: str, max_requests: int, window_seconds: int) -> None:
    now = time.time()
    entry = [t for t in RATE_LIMIT_FALLBACK.get(key, []) if now - t < window_seconds]
    if len(entry) >= max_requests:
        raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")
    entry.append(now)
    RATE_LIMIT_FALLBACK[key] = entry


def purge_rate_limits(older_than_seconds: int = 3600) -> int:
    """Чистка отработавших окон: строки копятся по одной на каждый IP."""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            "DELETE FROM rate_limits WHERE window_start < NOW() - make_interval(secs => %s) "
            "RETURNING key",
            (older_than_seconds,),
        )
        removed = len(c.fetchall())
        conn.commit()
    finally:
        conn.close()
    return removed


# ── Email ────────────────────────────────────────────────────────────────────

def _send_email(to_email: str, subject: str, html: str):
    """Отправка через Brevo. Общая для сброса пароля и подтверждения почты."""
    api_key = os.getenv("BREVO_API_KEY", "")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "")
    sender_name = os.getenv("BREVO_SENDER_NAME", "MediaHub")
    if not api_key:
        raise ValueError("BREVO_API_KEY не задан")
    if not sender_email:
        raise ValueError("BREVO_SENDER_EMAIL не задан")

    resp = http_requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html,
        },
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Brevo error {resp.status_code}: {resp.text}")


def _code_email_html(lead: str, code: str, note: str) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px">
      <h2 style="color:#4f46e5">MediaHub</h2>
      <p>{lead}</p>
      <div style="font-size:36px;font-weight:800;letter-spacing:12px;color:#4f46e5;padding:20px;background:#f0f0ff;border-radius:12px;text-align:center">{code}</div>
      <p style="color:#888;font-size:13px;margin-top:20px">{note}</p>
    </div>
    """


def send_reset_email(to_email: str, code: str):
    _send_email(
        to_email,
        "Сброс пароля — MediaHub",
        _code_email_html(
            "Вы запросили сброс пароля. Ваш код:",
            code,
            "Код действителен 15 минут. Если вы не запрашивали сброс — проигнорируйте это письмо.",
        ),
    )


def send_verification_email(to_email: str, code: str):
    _send_email(
        to_email,
        "Подтверждение регистрации — MediaHub",
        _code_email_html(
            "Вы регистрируетесь в MediaHub. Код подтверждения:",
            code,
            "Код действителен 15 минут. Если вы не регистрировались — просто проигнорируйте это письмо, "
            "аккаунт создан не будет.",
        ),
    )


# ── Group membership ────────────────────────────────────────────────────────

def require_group_member(group_id: int, user_id: int, conn) -> str:
    c = conn.cursor()
    c.execute("SELECT role FROM group_members WHERE group_id=%s AND user_id=%s", (group_id, user_id))
    row = c.fetchone()
    if not row:
        raise HTTPException(403, "Нет доступа к этой группе")
    return row["role"]


def check_invite_usable(token: str, conn) -> dict:
    """
    Проверяет ссылку, ничего не расходуя. Нужна на первом шаге регистрации:
    про мёртвое приглашение честнее сказать сразу, а не после письма с кодом.

    Возвращает строку invite_links.
    """
    c = conn.cursor()
    c.execute(
        "SELECT group_id, role, expires_at, max_uses, used_count FROM invite_links WHERE token=%s",
        (token,),
    )
    link = c.fetchone()
    if not link:
        raise HTTPException(404, "Ссылка приглашения не найдена")
    if link["expires_at"] < datetime.now(UTC):
        raise HTTPException(410, "Ссылка приглашения истекла")
    if link["max_uses"] is not None and link["used_count"] >= link["max_uses"]:
        raise HTTPException(410, "Лимит использований ссылки исчерпан")
    return link


def redeem_invite(token: str, user_id: int, conn) -> dict:
    """
    Единственный способ попасть в чужую группу — принять действующее приглашение.
    Используется и при регистрации по ссылке, и при приёме уже залогиненным
    пользователем: логика проверок должна быть одна, иначе разъедется.

    Возвращает {"group_id": int, "role": str}.
    """
    c = conn.cursor()
    link = check_invite_usable(token, conn)

    c.execute("SELECT 1 FROM group_members WHERE group_id=%s AND user_id=%s", (link["group_id"], user_id))
    if c.fetchone():
        raise HTTPException(409, "Вы уже участник этой группы")

    # Счётчик увеличиваем одним запросом с проверкой лимита: раздельные
    # «прочитать и сравнить» позволяли превысить max_uses при одновременных
    # переходах по одной ссылке.
    c.execute(
        "UPDATE invite_links SET used_count = used_count + 1 "
        "WHERE token=%s AND (max_uses IS NULL OR used_count < max_uses) RETURNING id",
        (token,),
    )
    if not c.fetchone():
        raise HTTPException(410, "Лимит использований ссылки исчерпан")

    c.execute(
        "INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, %s)",
        (link["group_id"], user_id, link["role"]),
    )
    return {"group_id": link["group_id"], "role": link["role"]}


# Две системы ролей, и путать их нельзя:
#   GLOBAL_ROLES  — про администрирование системы (users.role). Решает доступ к
#                   спискам пользователей и глобальным настройкам, и только.
#   GROUP_ROLES   — про работу с контентом внутри группы (group_members.role).
#                   Именно они определяют, кто может писать и публиковать.
# Раньше значения совпадали по названиям и означали разное; теперь пересечение
# только в слове «admin», и то в разных таблицах.
GLOBAL_ROLES = ("admin", "member")
GROUP_ROLES = ("admin", "editor", "volunteer")


def require_admin(user_id: int, conn) -> None:
    """Глобальная роль admin — для операций вне контекста группы."""
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=%s", (user_id,))
    row = c.fetchone()
    if not row or row["role"] != "admin":
        raise HTTPException(403, "Требуются права администратора")


def user_group_ids(user_id: int, conn) -> list[int]:
    c = conn.cursor()
    c.execute("SELECT group_id FROM group_members WHERE user_id=%s", (user_id,))
    return [r["group_id"] for r in c.fetchall()]


def posts_scope(user_id: int, conn, alias: str = "p") -> tuple:
    """
    SQL-фильтр «посты, доступные пользователю»: посты его групп плюс его собственные
    посты без группы. Возвращает (условие, параметры) для подстановки в WHERE.
    """
    prefix = f"{alias}." if alias else ""
    ids = user_group_ids(user_id, conn)
    own = f"({prefix}group_id IS NULL AND {prefix}author_id=%s)"
    if not ids:
        return own, [user_id]
    return f"({prefix}group_id = ANY(%s) OR {own})", [ids, user_id]


def require_post_access(post_id: int, user_id: int, conn, write: bool = False):
    """
    Отдаёт пост, если пользователь состоит в его группе (или это его собственный
    пост без группы). При write=True волонтёрам отказывает — как в групповых роутах.
    """
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    post = c.fetchone()
    if not post:
        raise HTTPException(404, "Пост не найден")
    if post["group_id"] is None:
        if post["author_id"] != user_id:
            raise HTTPException(403, "Нет доступа к этому посту")
        return post
    role = require_group_member(post["group_id"], user_id, conn)
    if write and role == "volunteer":
        raise HTTPException(403, "Недостаточно прав")
    return post


# ── Distance ─────────────────────────────────────────────────────────────────

def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(2 * radius * asin(sqrt(a)), 2)


# ── Upload configuration ─────────────────────────────────────────────────────

# Куда складывать загруженные файлы. Диск контейнера на Railway пересоздаётся
# при каждой выкатке, поэтому в проде сюда указывают смонтированный том
# (UPLOAD_DIR=/data/uploads) — иначе все картинки и видео постов исчезают
# при первом же деплое. По умолчанию — папка рядом с кодом, для локальной работы.
DEFAULT_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "").strip() or DEFAULT_UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-msvideo"}
ALLOWED_DOC_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
}
MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_DOC_SIZE = 50 * 1024 * 1024     # 50 MB


# ── AI prompts ───────────────────────────────────────────────────────────────

_AI_PROMPTS = {
    "creative": (
        "Ты — опытный SMM-редактор молодёжного центра. Перепиши текст так, чтобы он "
        "цеплял аудиторию 16–30 лет с первой строки: замени канцеляризмы живыми словами, "
        "добавь энергию и искренние эмоции, сделай ритм лёгким и читаемым. "
        "Вставь эмодзи там, где они усиливают смысл или настроение — не переусердствуй, "
        "1–3 эмодзи в нужных местах лучше, чем россыпь везде. "
        "Сохрани все факты, даты, имена и длину оригинала. "
        "Верни только готовый текст, без комментариев и пояснений."
    ),
    "formal": (
        "Ты — пресс-секретарь молодёжного центра с опытом работы в госструктурах. "
        "Перепиши текст в официальном, но живом стиле: грамотно, структурированно, "
        "без сленга и излишней эмоциональности, но и без бюрократической сухости. "
        "Используй чёткие формулировки, активный залог, уважительный тон. "
        "Текст должен подходить для официальных анонсов, партнёрских постов и отчётов. "
        "Сохрани все факты и структуру. Верни только готовый текст, без пояснений."
    ),
    "calltoaction": (
        "Ты — копирайтер молодёжного центра. Оставь основной текст без изменений "
        "и добавь в конец яркий, мотивирующий призыв к действию для аудитории 16–30 лет. "
        "Выбери глагол по смыслу поста: записаться, прийти, написать нам, подать заявку, "
        "узнать подробнее, поделиться с друзьями — и т.д. "
        "Тон — дружеский и воодушевляющий, без давления и манипуляций. "
        "Добавь 1–2 уместных эмодзи в призыв, чтобы он выделялся визуально. "
        "Верни полный текст с добавленным призывом, без комментариев."
    ),
    "shortify": (
        "Ты — редактор с острым чувством слова. Сократи текст примерно вдвое: "
        "безжалостно убери воду, повторы, лишние вводные слова и затянутые конструкции. "
        "Сохрани главную мысль, все ключевые факты (даты, имена, цифры) и живой тон. "
        "Не добавляй ничего нового. Верни только сокращённый вариант, без пояснений."
    ),
    "hashtags": (
        "Ты — SMM-специалист молодёжного центра. Проанализируй тему поста и придумай "
        "5–7 релевантных хештегов: микс из широких (#молодёжь, #события) и нишевых "
        "(по конкретной теме поста). Часть хештегов — на русском, часть — на английском. "
        "Хештеги должны реально использоваться в ВКонтакте и Telegram. "
        "Верни только хештеги через пробел, без текста поста и без пояснений."
    ),
    "russify": (
        "Ты — редактор русского языка. Пройдись по тексту и замени все англицизмы, "
        "заимствованный сленг и кальки на естественные русские аналоги, которые не режут слух. "
        "Примеры: контент → материал, дедлайн → срок, фидбек → отклик, "
        "постить → публиковать, ивент → мероприятие, воркшоп → мастер-класс. "
        "Сохрани стиль, тон и структуру текста. Имена, названия и аббревиатуры не трогай. "
        "Верни только исправленный текст, без пояснений и списка замен."
    ),
}


# ── VK API helpers ───────────────────────────────────────────────────────────

VK_API_VERSION = "5.199"


def vk_get_group_name(access_token: str, group_id: str) -> str:
    clean_id = group_id.lstrip("-")
    try:
        r = http_requests.get(
            "https://api.vk.com/method/groups.getById",
            params={"group_ids": clean_id, "access_token": access_token, "v": VK_API_VERSION},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            raise ValueError(data["error"].get("error_msg", "VK API error"))
        response = data.get("response", {})
        groups = response if isinstance(response, list) else response.get("groups", [])
        if not groups:
            raise ValueError("Группа не найдена")
        return groups[0].get("name", "")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Ошибка связи с VK: {e}")


def vk_upload_photo_to_wall(access_token: str, group_id: str, image_data: bytes, filename: str = "photo.jpg") -> str:
    clean_id = group_id.lstrip("-")
    r = http_requests.get(
        "https://api.vk.com/method/photos.getWallUploadServer",
        params={"group_id": clean_id, "access_token": access_token, "v": VK_API_VERSION},
        timeout=10,
    )
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"].get("error_msg", "VK getWallUploadServer error"))
    upload_url = data["response"]["upload_url"]

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
    content_type = mime_map.get(ext, "image/jpeg")

    r2 = http_requests.post(upload_url, files={"photo": (filename, image_data, content_type)}, timeout=60)
    r2.raise_for_status()
    upload_result = r2.json()
    if "error" in upload_result:
        err = upload_result["error"]
        raise ValueError(err if isinstance(err, str) else str(err))
    if not upload_result.get("photo") or not upload_result.get("server"):
        raise ValueError(f"Неожиданный ответ от VK при загрузке фото: {upload_result}")

    r3 = http_requests.post(
        "https://api.vk.com/method/photos.saveWallPhoto",
        data={
            "group_id": clean_id,
            "photo": upload_result["photo"],
            "server": upload_result["server"],
            "hash": upload_result["hash"],
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    saved = r3.json()
    if "error" in saved:
        raise ValueError(saved["error"].get("error_msg", "VK saveWallPhoto error"))
    photo = saved["response"][0]
    return f"photo{photo['owner_id']}_{photo['id']}"


def vk_upload_video_to_wall(access_token: str, group_id: str, video_data: bytes, filename: str = "video.mp4", title: str = "", description: str = "") -> str:
    clean_id = group_id.lstrip("-")
    r = http_requests.post(
        "https://api.vk.com/method/video.save",
        data={
            "group_id": clean_id,
            "name": title or filename,
            "description": description,
            "wallpost": 0,
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"].get("error_msg", "VK video.save error"))
    resp = data["response"]
    upload_url = resp["upload_url"]
    owner_id = resp["owner_id"]
    video_id = resp["video_id"]

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    mime_map = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm", "avi": "video/x-msvideo", "mkv": "video/x-matroska"}
    content_type = mime_map.get(ext, "video/mp4")

    r2 = http_requests.post(upload_url, files={"video_file": (filename, video_data, content_type)}, timeout=600)
    r2.raise_for_status()
    upload_result = r2.json()
    if "error" in upload_result:
        err = upload_result["error"]
        raise ValueError(err if isinstance(err, str) else str(err))

    return f"video{owner_id}_{video_id}"


def vk_upload_doc_to_wall(access_token: str, group_id: str, doc_data: bytes, filename: str = "doc.pdf", title: str = "") -> str:
    clean_id = group_id.lstrip("-")
    r = http_requests.get(
        "https://api.vk.com/method/docs.getWallUploadServer",
        params={"group_id": clean_id, "access_token": access_token, "v": VK_API_VERSION},
        timeout=10,
    )
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"].get("error_msg", "VK docs.getWallUploadServer error"))
    upload_url = data["response"]["upload_url"]

    r2 = http_requests.post(upload_url, files={"file": (filename, doc_data, "application/octet-stream")}, timeout=300)
    r2.raise_for_status()
    upload_result = r2.json()
    if "error" in upload_result:
        err = upload_result["error"]
        raise ValueError(err if isinstance(err, str) else str(err))
    if not upload_result.get("file"):
        raise ValueError(f"Неожиданный ответ от VK при загрузке документа: {upload_result}")

    r3 = http_requests.post(
        "https://api.vk.com/method/docs.save",
        data={
            "file": upload_result["file"],
            "title": title or filename,
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    saved = r3.json()
    if "error" in saved:
        raise ValueError(saved["error"].get("error_msg", "VK docs.save error"))
    resp = saved["response"]
    doc = resp["doc"] if isinstance(resp, dict) and "doc" in resp else (resp[0] if isinstance(resp, list) else resp)
    return f"doc{doc['owner_id']}_{doc['id']}"


def vk_wall_post(access_token: str, group_id: str, message: str, attachments: list[str] | None = None) -> int:
    attachments = attachments or []
    clean_id = group_id.lstrip("-")
    params: dict = {
        "owner_id": f"-{clean_id}",
        "from_group": 1,
        "message": message,
        "access_token": access_token,
        "v": VK_API_VERSION,
    }
    if attachments:
        params["attachments"] = ",".join(attachments)
    r = http_requests.post(
        "https://api.vk.com/method/wall.post",
        data=params,
        timeout=15,
    )
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"].get("error_msg", "VK wall.post error"))
    return data["response"]["post_id"]


# ── Telegram API helpers ─────────────────────────────────────────────────────

TG_CAPTION_LIMIT = 1024
TG_MESSAGE_LIMIT = 4096


def tg_api(bot_token: str, method: str, **kwargs) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    r = http_requests.post(url, timeout=kwargs.pop("_timeout", 30), **kwargs)
    try:
        data = r.json()
    except Exception:
        raise ValueError(f"Некорректный ответ Telegram ({r.status_code})")
    if not data.get("ok"):
        raise ValueError(data.get("description", "Telegram API error"))
    return data["result"]


def tg_get_chat_title(bot_token: str, chat_id: str) -> str:
    res = tg_api(bot_token, "getChat", data={"chat_id": chat_id})
    return res.get("title") or res.get("username") or str(res.get("id", ""))


def _resolve_media_bytes(item: dict, backend_base: str) -> tuple[bytes, str]:
    fname = upload_filename(item["url"])
    fpath = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, "rb") as f:
            return f.read(), item.get("filename") or fname
    if not backend_base:
        raise ValueError(
            f"Файла {fname} нет в {UPLOAD_DIR}, а забрать его по сети неоткуда: "
            "не задан BACKEND_URL. Проверьте UPLOAD_DIR — скорее всего "
            "приложение смотрит не в тот каталог."
        )
    file_url = f"{backend_base}{item['url']}"
    resp = http_requests.get(file_url, timeout=120)
    resp.raise_for_status()
    return resp.content, item.get("filename") or fname



def _remember_message(posted_ids: list[int], response) -> None:
    """
    Запоминает идентификатор отправленного сообщения.

    Ответ без message_id — не повод класть в tg_message_ids дырку: по этому
    списку потом ищутся реакции (`tg_message_ids @> [id]`), и null в нём просто
    мусор.
    """
    message_id = (response or {}).get("message_id")
    if isinstance(message_id, int):
        posted_ids.append(message_id)


def tg_send_post(bot_token: str, chat_id: str, message: str, media: list[dict], backend_base: str) -> list[int]:
    """
    Отправляет пост в канал. Текст приходит с разметкой ссылок `[текст](адрес)`.

    Разметка разворачивается в HTML прямо здесь, а не раньше: предел длины у
    Telegram считается по видимым символам, и резать по нему уже готовый HTML
    значит разрывать теги пополам. Поэтому режем исходную разметку, а в HTML
    превращаем каждый кусок отдельно.
    """
    photos_videos = [m for m in media if m.get("type") in ("image", "video")]
    docs = [m for m in media if m.get("type") == "doc"]
    posted_ids: list[int] = []

    def caption(text: str) -> dict:
        """Подпись к медиа: обрезанная по видимой длине и уже в HTML."""
        return {"caption": richtext.to_html(richtext.truncate(text, TG_CAPTION_LIMIT)),
                "parse_mode": "HTML"}

    caption_with_media = (richtext.visible_length(message) <= TG_CAPTION_LIMIT
                          and (photos_videos or docs))
    sent_text_separately = False

    if message and not caption_with_media:
        for chunk in richtext.chunks(message, TG_MESSAGE_LIMIT):
            res = tg_api(bot_token, "sendMessage", data={
                "chat_id": chat_id, "text": richtext.to_html(chunk), "parse_mode": "HTML"})
            _remember_message(posted_ids, res)
        sent_text_separately = True

    if photos_videos:
        if len(photos_videos) == 1:
            item = photos_videos[0]
            file_bytes, fname = _resolve_media_bytes(item, backend_base)
            method = "sendPhoto" if item["type"] == "image" else "sendVideo"
            field = "photo" if item["type"] == "image" else "video"
            data = {"chat_id": chat_id}
            if not sent_text_separately and message:
                data.update(caption(message))
            res = tg_api(bot_token, method, data=data, files={field: (fname, file_bytes)}, _timeout=300)
            _remember_message(posted_ids, res)
        else:
            files = {}
            media_payload = []
            for idx, item in enumerate(photos_videos[:10]):
                file_bytes, fname = _resolve_media_bytes(item, backend_base)
                attach_key = f"file{idx}"
                files[attach_key] = (fname, file_bytes)
                m = {"type": "photo" if item["type"] == "image" else "video", "media": f"attach://{attach_key}"}
                if idx == 0 and not sent_text_separately and message:
                    m.update(caption(message))
                media_payload.append(m)
            res = tg_api(
                bot_token, "sendMediaGroup",
                data={"chat_id": chat_id, "media": json.dumps(media_payload)},
                files=files, _timeout=600,
            )
            if isinstance(res, list):
                for m in res:
                    _remember_message(posted_ids, m)

    for idx, item in enumerate(docs):
        file_bytes, fname = _resolve_media_bytes(item, backend_base)
        data = {"chat_id": chat_id}
        if idx == 0 and not sent_text_separately and not photos_videos and message:
            data.update(caption(message))
        res = tg_api(bot_token, "sendDocument", data=data, files={"document": (fname, file_bytes)}, _timeout=300)
        _remember_message(posted_ids, res)

    if not posted_ids and message:
        res = tg_api(bot_token, "sendMessage", data={
            "chat_id": chat_id,
            "text": richtext.to_html(richtext.truncate(message, TG_MESSAGE_LIMIT)),
            "parse_mode": "HTML"})
        _remember_message(posted_ids, res)

    return posted_ids


# ── Youth centers mock data ──────────────────────────────────────────────────

YOUTH_CENTERS_MOCK: list[dict] = [
    {"id": 1, "name": "Молодёжный творческий бизнес-центр «Пилот»", "address": "ул. Аэровокзальная, 9", "coordinates": [56.007231, 92.872375]},
    {"id": 2, "name": "Молодёжный центр «Зеркало»", "address": "ул. Бограда, 65", "coordinates": [56.007156, 92.857835]},
    {"id": 3, "name": "Молодёжный центр «Новые имена»", "address": "пр. им. газеты «Красноярский рабочий», 68", "coordinates": [56.019088, 92.932854]},
    {"id": 4, "name": "Молодёжный центр «Июнь»", "address": "ул. Ленина, 115", "coordinates": [56.010575, 92.865362]},
    {"id": 5, "name": "Молодёжный военно-спортивный центр «Патриот»", "address": "ул. Конституции СССР, 1", "coordinates": [56.005219, 92.960000]},
    {"id": 6, "name": "Молодёжный центр «Центр карьеры»", "address": "ул. Кирова, 37", "coordinates": [56.012195, 92.927296]},
    {"id": 7, "name": "Молодёжный центр «Центр медицинской профилактики»", "address": "ул. Парижской Коммуны, 39", "coordinates": [56.015254, 92.884495]},
    {"id": 8, "name": "Молодёжный центр творческого развития «Аврора»", "address": "ул. Мира, 8", "coordinates": [56.010580, 92.879484]},
    {"id": 9, "name": "Молодёжный центр «Альтернатива»", "address": "ул. Щорса, 53", "coordinates": [56.022198, 92.913971]},
    {"id": 10, "name": "Центр технического проектирования «ПроТехно»", "address": "ул. Алёши Тимошенкова, 87А", "coordinates": [55.970091, 92.941041]},
    {"id": 11, "name": "Центр путешественников", "address": "ул. Карла Маркса, 49", "coordinates": [56.010637, 92.880036]},
    {"id": 12, "name": "Трудовой отряд Главы города Красноярска", "address": "ул. Мичурина, 17", "coordinates": [56.006241, 92.962945]},
    {"id": 13, "name": "Центр авторского самоопределения молодёжи «Зеркало»", "address": "ул. Бограда, 65", "coordinates": [56.007156, 92.857835]},
    {"id": 14, "name": "Центр молодёжных инициатив «Форум»", "address": "остров Отдыха, 6", "coordinates": [55.994841, 92.872365]},
    {"id": 15, "name": "ЦОПП Красноярского края", "address": "ул. Партизана Железняка, 13", "coordinates": [56.031944, 92.922629]},
    {"id": 16, "name": "Кванториум", "address": "ул. Дубровинского, 1И", "coordinates": [56.009112, 92.888053]},
    {"id": 17, "name": "IT-Куб", "address": "ул. Железнодорожников, 22Д", "coordinates": [56.025183, 92.841650]},
    {"id": 18, "name": "Дом науки и техники", "address": "ул. Урицкого, 61", "coordinates": [56.009287, 92.875364]},
]


def vk_wall_create_comment(access_token: str, group_id: str, post_id, message: str,
                           reply_to_comment=None) -> int:
    """
    Первый комментарий под записью — от имени сообщества.

    `from_group` обязателен: без него комментарий уходит от лица человека, чей
    токен используется, и под записью центра появляется реплика постороннего.
    """
    clean_id = str(group_id).lstrip("-")
    r = http_requests.post(
        "https://api.vk.com/method/wall.createComment",
        data={
            "owner_id": f"-{clean_id}",
            "post_id": post_id,
            "from_group": clean_id,
            "message": message,
            # Без адресата ответ ложится отдельной репликой в конец ветки, и
            # человек не понимает, что отвечают именно ему.
            **({"reply_to_comment": reply_to_comment} if reply_to_comment else {}),
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"].get("error_msg", "VK wall.createComment error"))
    return data["response"]["comment_id"]


def vk_wall_delete(access_token: str, group_id: str, post_id: str | int) -> None:
    """
    Убирает запись со стены сообщества.

    Отдельно разбираем «записи уже нет»: пост могли снять руками в самом ВК, и
    для нас это не ошибка, а ровно тот результат, которого мы добивались.
    """
    clean_id = str(group_id).lstrip("-")
    r = http_requests.post(
        "https://api.vk.com/method/wall.delete",
        data={
            "owner_id": f"-{clean_id}",
            "post_id": post_id,
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    data = r.json()
    if "error" in data:
        message = data["error"].get("error_msg", "VK wall.delete error")
        if data["error"].get("error_code") in VK_ALREADY_GONE:
            return
        raise ValueError(message)


# Коды ВК, означающие «записи уже нет»: 210 — нет доступа к записи (в том
# числе к удалённой), 100 — неверный параметр, чем ВК отвечает на
# несуществующий post_id.
VK_ALREADY_GONE = (100, 210)


def tg_delete_messages(bot_token: str, chat_id: str, message_ids: list) -> None:
    """
    Удаляет сообщения канала. Бот обязан быть администратором с правом удаления.

    Отсутствующее сообщение пропускаем: сообщение могли удалить руками, и это
    не повод считать снятие неудавшимся.
    """
    for message_id in message_ids or []:
        try:
            tg_api(bot_token, "deleteMessage",
                   data={"chat_id": chat_id, "message_id": message_id})
        except ValueError as e:
            if "not found" in str(e).lower() or "message to delete" in str(e).lower():
                continue
            raise


def vk_get_comments(access_token: str, group_id: str, post_id, count: int = 100) -> dict:
    """
    Комментарии под записью вместе с именами авторов.

    `extended=1` просим не для красоты: без него в ответе только числовые
    идентификаторы, и очередь обращений показывала бы «id 42163» вместо имени
    человека — работать с такой очередью нельзя.

    Порядок `asc`: ответ считается ответом только на то, что было раньше него,
    и разбирать ветку удобнее с начала.
    """
    clean_id = str(group_id).lstrip("-")
    r = http_requests.get(
        "https://api.vk.com/method/wall.getComments",
        params={
            "owner_id": f"-{clean_id}",
            "post_id": post_id,
            "count": min(count, 100),
            "sort": "asc",
            "extended": 1,
            "need_likes": 0,
            # Ответы внутри веток тоже нужны: именно ими чаще всего и отвечают.
            "thread_items_count": 10,
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=20,
    )
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"].get("error_msg", "VK wall.getComments error"))
    return data["response"]
