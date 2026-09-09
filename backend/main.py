"""
MediaHub — Медиахаб для молодёжных центров
FastAPI + PostgreSQL backend
"""

import datetime
import logging
import os
import random
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from psycopg2.extras import Json

import health
import scheduler
from alembic import command
from alembic.config import Config
from logs import get_logger, new_request_id, request_id_var, setup_logging, user_id_var
from utils import (
    APP_TZ,
    DATABASE_URL,
    DEFAULT_UPLOAD_DIR,
    SECRET_PREFIX,
    UPLOAD_DIR,
    UPLOAD_NAME_RE,
    app_now,
    app_now_str,
    check_upload_signature,
    client_ip,
    encrypt_secret,
    get_db,
    hash_password,
    serve_disposition,
)

load_dotenv()
setup_logging()
log = get_logger("app")

app = FastAPI(title="MediaHub API", version="1.0.0")

ALLOWED_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,https://frontend-production-cd62.up.railway.app",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Логи запросов ────────────────────────────────────────────────────────────
# Одна строка на обращение: метод, путь, код, длительность, кто и какой запрос.
# Без этого о проде было известно ровно столько, сколько успел напечатать
# случайный print, и связать жалобу пользователя с записью в логе было нечем.

# Запрос дольше этого — уже не норма, о нём стоит знать до того, как он станет
# таймаутом. По умолчанию 2 секунды.
SLOW_REQUEST_MS = int(os.getenv("SLOW_REQUEST_MS", "2000"))

# Мониторинг ходит на /api/health постоянно, и в логе от этого нет пользы.
QUIET_PATHS = ("/api/health", "/")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    # Идентификатор берём из заголовка, если он пришёл: так запись у нас
    # сшивается с записью прокси или фронта по одному значению.
    request_id = request.headers.get("x-request-id", "").strip()[:64] or new_request_id()
    token = request_id_var.set(request_id)
    user_token = user_id_var.set(None)
    # Кладём и в состояние запроса: обработчик непойманной ошибки работает
    # снаружи этого middleware, когда контекст уже сброшен, а идентификатор
    # в ответе и в логе обязан быть один и тот же.
    request.state.request_id = request_id
    started = time.monotonic()
    try:
        response = await call_next(request)

        took_ms = round((time.monotonic() - started) * 1000, 1)
        response.headers["X-Request-Id"] = request_id
        if request.url.path in QUIET_PATHS:
            level = logging.DEBUG
        elif response.status_code >= 500 or took_ms > SLOW_REQUEST_MS:
            # Медленный ответ — ещё не отказ, но и не норма: о нём стоит знать
            # до того, как он станет таймаутом.
            level = logging.WARNING
        else:
            level = logging.INFO
        log.log(
            level,
            f"{request.method} {request.url.path} → {response.status_code} за {took_ms} мс",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": took_ms,
                # Идентификатор пользователя проставляет разбор токена, поэтому
                # читаем его здесь, а не в начале обработки.
                "user_id": getattr(request.state, "user_id", None),
                "ip": client_ip(request),
            },
        )
        return response
    finally:
        # Сбрасываем в самом конце: записи выше обязаны видеть контекст.
        request_id_var.reset(token)
        user_id_var.reset(user_token)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """
    Единый ответ на непойманную ошибку.

    Наружу уходит идентификатор запроса и ничего больше: тип исключения и
    трейсбек — это внутреннее устройство, ему в ответе не место. Зато по этому
    идентификатору запись находится в логе точным поиском, и человеку есть что
    назвать в обращении.
    """
    request_id = getattr(request.state, "request_id", None) or request_id_var.get() or new_request_id()
    log.exception(
        "необработанная ошибка",
        extra={"method": request.method, "path": request.url.path, "request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера. "
                      f"Если она повторяется, сообщите код обращения: {request_id}",
            "request_id": request_id,
        },
        headers={"X-Request-Id": request_id},
    )


# ── Routers ──────────────────────────────────────────────────────────────────

from routers.analytics import router as analytics_router
from routers.audit_log import router as audit_router
from routers.auth import router as auth_router
from routers.comments import router as comments_router
from routers.groups import router as groups_router
from routers.notifications import router as notifications_router
from routers.posts import router as posts_router
from routers.settings import router as settings_router
from routers.upload import router as upload_router
from routers.users import router as users_router
from routers.volunteer_media import router as volunteer_media_router
from routers.yc import router as yc_router

app.include_router(auth_router)
app.include_router(posts_router)
app.include_router(groups_router)
app.include_router(settings_router)
app.include_router(volunteer_media_router)
app.include_router(notifications_router)
app.include_router(analytics_router)
app.include_router(comments_router)
app.include_router(users_router)
app.include_router(yc_router)
app.include_router(upload_router)
app.include_router(audit_router)


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "MediaHub API"}


@app.get("/api/health")
def healthcheck():
    """
    Состояние сервиса для мониторинга: 200 — всё в порядке, 503 — нет.

    Без авторизации: аптайм-чекер ходит без токена. Наружу уходят только флаги
    и счётчики, ничего чувствительного.
    """
    report, ok = health.collect()
    return JSONResponse(status_code=200 if ok else 503, content=report)


# ── Схема БД ─────────────────────────────────────────────────────────────────
# Единственный источник правды по схеме — миграции alembic (alembic/versions/).
# Здесь только их запуск; CREATE TABLE руками добавлять нельзя — новую колонку
# заводите через `alembic revision`, иначе схема снова разъедется.

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ревизия, описывающая схему в том виде, в каком её создавал прежний init_db().
# База, поднятая до перехода на alembic, помечается этой ревизией без повторного
# применения DDL — таблицы в ней уже есть.
BASELINE_REVISION = "3ee67a8c2e29"


def _alembic_config() -> Config:
    cfg = Config(os.path.join(BASE_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BASE_DIR, "alembic"))
    # URL передаём через attributes, а не set_main_option: ConfigParser
    # интерполирует «%», и URL-encoded пароль (Railway) сломал бы запуск.
    cfg.attributes["db_url"] = DATABASE_URL
    return cfg


# Объекты, которые прежний init_db() добавлял в последнюю очередь (ALTER TABLE
# и поздние CREATE TABLE). Если база «дореформенная», но чего-то из этого нет,
# значит она отстаёт от baseline-ревизии и помечать её нельзя — молча
# проштампованная неполная схема даст 500-е уже в рантайме.
BASELINE_REQUIRED = [
    ("users", "password_hash"),
    ("posts", "media"),
    ("posts", "location_address"),
    ("posts", "location_lat"),
    ("posts", "location_lng"),
    ("posts", "group_id"),
    ("posts", "vk_post_id"),
    ("posts", "tg_message_ids"),
    ("posts", "vk_stats_updated_at"),
    ("notifications", "group_id"),
    ("vk_settings", "workspace_id"),
    ("tg_settings", "workspace_id"),
    ("groups", "id"),
    ("group_members", "id"),
    ("invite_links", "id"),
    ("volunteer_media", "id"),
]


def _assert_matches_baseline(conn):
    c = conn.cursor()
    c.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'"
    )
    present = {(r["table_name"], r["column_name"]) for r in c.fetchall()}
    missing = [f"{t}.{col}" for t, col in BASELINE_REQUIRED if (t, col) not in present]
    if missing:
        raise RuntimeError(
            "База выглядит созданной до перехода на alembic, но не дотягивает до "
            f"ревизии {BASELINE_REVISION}. Не хватает: {', '.join(missing)}. "
            "Пометить её базовой ревизией нельзя — приведите схему вручную "
            "или снимите дамп и обратитесь к миграциям."
        )


# Ключ консультативной блокировки: любое число, лишь бы одно и то же во всех
# процессах. Postgres сериализует их между собой сам.
MIGRATION_LOCK_ID = 8_150_2026


def schema_is_current() -> tuple[bool, str]:
    """Доехала ли база до последней ревизии. Ничего не меняет."""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT to_regclass('public.alembic_version') IS NOT NULL AS versioned")
        if not c.fetchone()["versioned"]:
            return False, "база не размечена alembic — выполните `python manage.py migrate`"
        c.execute("SELECT version_num FROM alembic_version")
        row = c.fetchone()
        current = row["version_num"] if row else None
    finally:
        conn.close()
    if current == head:
        return True, f"схема на последней ревизии ({head})"
    return False, (
        f"схема отстала: в базе {current}, ожидается {head}. "
        "Выполните `python manage.py migrate` (на Railway это preDeployCommand)."
    )


def run_migrations():
    """
    Накатывает миграции под консультативной блокировкой.

    Блокировка нужна, даже когда команда одна: на Railway новый контейнер
    поднимается раньше, чем снят старый, а при масштабировании инстансов будет
    несколько. Двое одновременно накатывающих alembic — это гонка за
    alembic_version и наполовину применённая схема.
    """
    lock = get_db()
    lock.cursor().execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
    try:
        _run_migrations_locked()
    finally:
        lock.cursor().execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
        lock.close()


def _run_migrations_locked():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT to_regclass('public.alembic_version') IS NOT NULL AS versioned, "
        "       to_regclass('public.users') IS NOT NULL AS legacy"
    )
    state = c.fetchone()

    cfg = _alembic_config()
    if state["legacy"] and not state["versioned"]:
        _assert_matches_baseline(conn)
        conn.close()
        command.stamp(cfg, BASELINE_REVISION)
        log.info(f"alembic: существующая схема помечена ревизией {BASELINE_REVISION}")
    else:
        conn.close()
    command.upgrade(cfg, "head")


# ── Демо-данные ──────────────────────────────────────────────────────────────

def seed_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()["count"] == 0:
        c.executemany(
            "INSERT INTO users (name, email, role, avatar, password_hash) VALUES (%s, %s, %s, %s, %s)",
            [
                ("Алексей Иванов", "admin@mediahub.ru", "admin", "АИ", hash_password("admin123!")),
                ("Мария Петрова", "editor@mediahub.ru", "member", "МП", hash_password("editor123!")),
                ("Екатерина Волонтёр", "volunteer@mediahub.ru", "member", "ЕВ", hash_password("volunteer123!")),
            ],
        )

    c.execute("SELECT COUNT(*) FROM templates")
    if c.fetchone()["count"] == 0:
        c.executemany(
            "INSERT INTO templates (name, type, description, fields, template_text) VALUES (%s, %s, %s, %s, %s)",
            [
                ("Анонс мероприятия", "announcement", "Объявление о предстоящем событии",
                 Json([
                     {"key": "event_name", "label": "Название мероприятия", "placeholder": "Хакатон «IT-Кубок»"},
                     {"key": "date", "label": "Дата и время", "placeholder": "25 апреля, 10:00"},
                     {"key": "location", "label": "Место проведения", "placeholder": "МЦ «Зеркало»"},
                     {"key": "description", "label": "Краткое описание", "placeholder": "Соревнования по программированию"},
                     {"key": "contact", "label": "Контакт для записи", "placeholder": "@smm_manager"},
                 ]),
                 "🔥 {event_name}\n\n📅 Дата: {date}\n📍 Место: {location}\n\n{description}\n\n👉 Успей зарегистрироваться! Контакт: {contact}\n\n#мероприятие #молодёжь #красноярск"),
                ("Итоги события", "results", "Публикация результатов прошедшего мероприятия",
                 Json([
                     {"key": "event_name", "label": "Название мероприятия", "placeholder": "Форум молодых лидеров"},
                     {"key": "participants", "label": "Кол-во участников", "placeholder": "150"},
                     {"key": "highlights", "label": "Главные моменты", "placeholder": "5 спикеров, мастер-классы"},
                     {"key": "next_event", "label": "Следующее мероприятие", "placeholder": "Следующий форум — в июне"},
                 ]),
                 "✅ {event_name} — позади!\n\n👥 Участников: {participants}\n\n🎯 {highlights}\n\nСпасибо всем! {next_event} — следите за анонсами.\n\n#итоги #молодёжь #красноярск"),
                ("Вакансия", "vacancy", "Объявление об открытой позиции",
                 Json([
                     {"key": "position", "label": "Должность", "placeholder": "SMM-менеджер"},
                     {"key": "organization", "label": "Организация", "placeholder": "МЦ «Зеркало»"},
                     {"key": "requirements", "label": "Требования", "placeholder": "Опыт от 1 года"},
                     {"key": "conditions", "label": "Условия", "placeholder": "Гибкий график"},
                     {"key": "contact", "label": "Контакт", "placeholder": "@hr_manager"},
                 ]),
                 "🚀 Вакансия: {position}\n🏢 {organization}\n\n📋 Требования:\n{requirements}\n\n💼 Условия:\n{conditions}\n\n📩 Откликнуться: {contact}\n\n#вакансия #работа #красноярск"),
                ("Грант", "grant", "Информация о грантовой программе",
                 Json([
                     {"key": "grant_name", "label": "Название гранта", "placeholder": "Грант «Молодёжь края»"},
                     {"key": "amount", "label": "Размер поддержки", "placeholder": "до 500 000 ₽"},
                     {"key": "deadline", "label": "Дедлайн подачи", "placeholder": "1 мая 2026"},
                     {"key": "who", "label": "Для кого", "placeholder": "НКО и молодёжные орг."},
                     {"key": "link", "label": "Ссылка", "placeholder": "grant.krasn.ru"},
                 ]),
                 "💰 {grant_name}\n\n🎁 Поддержка: {amount}\n⏰ Дедлайн: {deadline}\n\n👥 Для кого: {who}\n\n🔗 Подробнее: {link}\n\n#грант #поддержка #молодёжь"),
            ],
        )

    c.execute("SELECT COUNT(*) FROM posts")
    if c.fetchone()["count"] == 0:
        now = app_now()
        rows = [
            ("🔥 Хакатон IT-Кубок — регистрация открыта!",
             "🔥 Хакатон IT-Кубок\n\n📅 Дата: 25–26 апреля, 10:00\n📍 Место: Каменка\n\nСоревнования по программированию.\n\n👉 @it_kubok\n\n#мероприятие #молодёжь",
             "published", ["vk", "telegram"], ["мероприятия"], -7, "announcement"),
            ("✅ Форум молодых лидеров — итоги!",
             "✅ Форум молодых лидеров — позади!\n\n👥 Участников: 200\n\n🎯 7 спикеров, 4 мастер-класса.\n\n#итоги #молодёжь",
             "published", ["vk"], ["мероприятия"], -14, "results"),
            ("🚀 Вакансия: SMM-менеджер в МЦ «Зеркало»",
             "🚀 SMM-менеджер\n🏢 МЦ «Зеркало»\n\n📋 Опыт от 1 года\n💼 Гибкий график\n📩 @hr_zerkalo\n\n#вакансия",
             "published", ["vk", "telegram"], ["вакансии"], -5, "vacancy"),
            ("💰 Грант «Молодёжь края» — подай заявку",
             "💰 Грант «Молодёжь края»\n\n🎁 до 500 000 ₽\n⏰ 1 мая 2026\n🔗 grant.krasn.ru\n\n#грант",
             "published", ["vk"], ["гранты"], -3, "grant"),
            ("🌟 Волонтёрская смена — набор участников",
             "🌟 Волонтёрская смена 2026\n\n📅 1–7 июня\n📍 Столбы\n\n#волонтёр",
             "scheduled", ["vk", "telegram"], ["мероприятия"], 2, "announcement"),
            ("📊 Итоги апреля — наша статистика",
             "📊 Апрель:\n\n✅ 24 публикации\n👥 Охват: 1 200\n❤️ Вовлечённость: 8.3%\n\n#статистика",
             "scheduled", ["vk"], ["новости"], 1, None),
            ("🎓 Интенсив «Стартап за 48 часов»",
             "🎓 Интенсив «Стартап за 48 часов»\n\n📅 10 мая\n📍 Краевой дворец молодёжи\n\n#стартап",
             "draft", ["vk", "telegram"], ["мероприятия"], 5, "announcement"),
            ("🏋️ Спортивный фестиваль «Активная молодёжь»",
             "🏋️ «Активная молодёжь»\n\n📅 18 мая\n📍 Стадион «Рассвет»\n\n#спорт",
             "draft", ["vk"], ["мероприятия"], 10, None),
        ]
        for title, content, status, platforms, tags, days, tmpl in rows:
            dt = now + datetime.timedelta(days=days)
            scheduled_at = dt.strftime("%Y-%m-%dT%H:%M") if status == "scheduled" else None
            published_at = dt.strftime("%Y-%m-%dT%H:%M") if status == "published" else None
            created_at = (now + datetime.timedelta(days=days - 1)).strftime("%Y-%m-%dT%H:%M")
            c.execute(
                "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,"
                "published_at,author_id,template_type,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (title, content, status, Json(platforms), Json(tags),
                 scheduled_at, published_at, random.choice([1, 2]), tmpl, created_at),
            )

        c.executemany(
            "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, %s)",
            [
                (1, "Пост «Хакатон IT-Кубок» опубликован", "success", 0),
                (1, "Запланирован пост на завтра: «Итоги апреля»", "info", 0),
                (1, "Черновик «Спортивный фестиваль» не опубликован 5 дней", "warning", 1),
                (2, "Новый пост на модерации от волонтёра", "info", 0),
            ],
        )

    c.execute("SELECT COUNT(*) FROM groups")
    if c.fetchone()["count"] == 0:
        c.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
        first_user_row = c.fetchone()
        if first_user_row:
            first_user_id = first_user_row["id"]
            c.execute(
                "INSERT INTO groups (name, description, created_by) VALUES (%s, %s, %s) RETURNING id",
                ("Медиа-Хаб", "Группа по умолчанию", first_user_id),
            )
            gid = c.fetchone()["id"]

            c.execute("SELECT id FROM users")
            for u in c.fetchall():
                c.execute(
                    "INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'admin') ON CONFLICT DO NOTHING",
                    (gid, u["id"]),
                )

            c.execute("UPDATE posts SET group_id=%s WHERE group_id IS NULL", (gid,))
            c.execute("UPDATE notifications SET group_id=%s WHERE group_id IS NULL", (gid,))
            c.execute("UPDATE vk_settings SET workspace_id=%s WHERE workspace_id IS NULL", (gid,))
            c.execute("UPDATE tg_settings SET workspace_id=%s WHERE workspace_id IS NULL", (gid,))

    conn.commit()
    conn.close()


def encrypt_existing_secrets():
    """
    Дошифровывает токены соцсетей, записанные до включения шифрования.

    Чтение умеет и открытый текст, так что без этого ничего не сломается — но
    тогда старые токены так и лежали бы в базе голыми. Операция идемпотентна:
    строки с префиксом пропускаются, поэтому её безопасно гонять при каждом
    старте, в том числе после разворачивания старого дампа.
    """
    conn = get_db()
    c = conn.cursor()
    encrypted = 0
    for table, column in (("vk_settings", "access_token"), ("tg_settings", "bot_token")):
        c.execute(
            f"SELECT id, {column} AS secret FROM {table} "  # noqa: S608 — имена свои, не из ввода
            f"WHERE {column} IS NOT NULL AND {column} <> '' "
            f"AND {column} NOT LIKE %s",
            (SECRET_PREFIX + "%",),
        )
        for row in c.fetchall():
            c.execute(
                f"UPDATE {table} SET {column}=%s WHERE id=%s",  # noqa: S608
                (encrypt_secret(row["secret"]), row["id"]),
            )
            encrypted += 1
    conn.commit()
    conn.close()
    if encrypted:
        log.info(f"🔒  зашифровано токенов интеграций: {encrypted}")


def ensure_admin_exists() -> bool:
    """
    Следит, что в системе есть администратор, который может войти.

    Глобальную роль назначает только другой администратор, а регистрация всем
    выдаёт editor. Значит, стоит остаться без рабочего админа — и назначить
    нового будет физически некем: управление пользователями закроется навсегда.
    Посевной admin@mediahub.ru эту роль не спасает, у него пустой пароль.

    BOOTSTRAP_ADMIN_EMAIL — способ выбраться: указываете почту существующего
    пользователя, при старте он получает роль admin. Операция идемпотентная,
    после неё переменную можно убрать.
    """
    conn = get_db()
    try:
        c = conn.cursor()
        bootstrap = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        if bootstrap:
            c.execute(
                "UPDATE users SET role='admin' WHERE email=%s AND role <> 'admin' RETURNING id",
                (bootstrap,),
            )
            promoted = c.fetchone()
            conn.commit()
            if promoted:
                log.info(f"👑  {bootstrap} назначен администратором (BOOTSTRAP_ADMIN_EMAIL)")
            else:
                c.execute("SELECT 1 FROM users WHERE email=%s", (bootstrap,))
                if not c.fetchone():
                    log.warning(
                        f"⚠️   BOOTSTRAP_ADMIN_EMAIL={bootstrap}: такого пользователя нет. "
                        "Сначала зарегистрируйтесь этой почтой."
                    )

        c.execute(
            "SELECT COUNT(*) FILTER (WHERE password_hash IS NOT NULL) AS usable, "
            "       COUNT(*) AS total FROM users WHERE role='admin'"
        )
        row = c.fetchone()
    finally:
        conn.close()

    if row["usable"]:
        return True
    log.warning(
        "⚠️   нет ни одного администратора, который может войти "
        f"(всего с ролью admin: {row['total']}). Назначить нового будет некому — "
        "задайте BOOTSTRAP_ADMIN_EMAIL с почтой существующего пользователя."
    )
    return False


def check_time_alignment() -> bool:
    """
    Сверяет часы приложения и базы.

    Раньше здесь проверялось совпадение часовых поясов: даты лежали строками
    без зоны, и достаточно было развести APP_TZ с зоной в server_default,
    чтобы в одной колонке оказались значения, различающиеся на часы. После
    перехода на timestamptz такой ошибки быть не может — колонка хранит
    абсолютный момент, а зона применяется только на выдаче.

    Остаётся то, что проверять всё ещё стоит: расхождение самих часов. Оно
    ломает и сроки публикации, и окна аналитики, а по данным замечается плохо.
    Не роняет приложение: перекос времени — повод громко предупредить.
    """
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT NOW() AS db_now")
        db_now = c.fetchone()["db_now"]
    finally:
        conn.close()

    drift = abs((db_now - app_now()).total_seconds()) / 60
    if drift > 5:
        log.warning(
            f"⚠️   часы базы и приложения расходятся на {drift:.0f} мин: "
            f"база считает {db_now.isoformat()}, приложение — {app_now().isoformat()}. "
            "Отложенные посты и окна аналитики будут смещаться."
        )
        return False
    log.info(f"🕒  время согласовано: {APP_TZ}, сейчас {app_now_str()}")
    return True


def check_upload_storage():
    """
    Говорит, куда реально легли загрузки, и проверяет, что туда можно писать.

    Без смонтированного тома каталог живёт внутри контейнера и пересоздаётся
    при каждой выкатке — все картинки и видео постов молча исчезают. Ошибку
    прав тоже лучше увидеть при старте, а не в момент первой загрузки.
    """
    probe = os.path.join(UPLOAD_DIR, ".write-probe")
    try:
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        raise RuntimeError(f"Каталог загрузок {UPLOAD_DIR} недоступен для записи: {e}")

    files = [n for n in os.listdir(UPLOAD_DIR) if not n.startswith(".")]
    if UPLOAD_DIR == DEFAULT_UPLOAD_DIR:
        log.warning(
            f"⚠️   загрузки: {UPLOAD_DIR} — каталог внутри контейнера. "
            "На Railway он пересоздаётся при каждой выкатке и файлы пропадут. "
            "Смонтируйте том и задайте UPLOAD_DIR."
        )
    else:
        log.info(f"📁  загрузки: {UPLOAD_DIR} (файлов: {len(files)})")


def check_ai_model() -> None:
    """
    Пишет в лог, какая модель настроена у ИИ-помощника.

    Поставщик выводит модели из обращения молча, и узнаём мы об этом от
    человека, у которого перестала работать кнопка. Строка в логе при старте
    даёт хотя бы точку отсчёта: видно, что именно мы просим, не заглядывая в
    переменные окружения работающего контейнера.
    """
    from routers.posts import DEFAULT_GROQ_MODEL, groq_model

    if not os.getenv("GROQ_API_KEY", "").strip():
        log.info("🤖  ИИ-помощник выключен: GROQ_API_KEY не задан")
        return
    model = groq_model()
    suffix = "" if os.getenv("GROQ_MODEL", "").strip() else " (умолчание)"
    log.info(f"🤖  ИИ-помощник: модель {model}{suffix}")
    if model == DEFAULT_GROQ_MODEL and not os.getenv("GROQ_MODEL", "").strip():
        log.info("     сменить можно переменной GROQ_MODEL, без выкатки")


def check_public_url() -> None:
    """
    Предупреждает, если собственный адрес приложения не задан.

    В соцсети медиа уходит байтами, поэтому при файлах на локальном диске
    адрес не нужен вовсе. Он выручает в одном случае: файла на диске не
    оказалось, и его надо забрать у себя же по HTTP. Ронять старт из-за этого
    нельзя, но сказать заранее стоит — иначе о нём вспомнят в тот момент,
    когда что-то уже пошло не так.
    """
    if os.getenv("BACKEND_URL", "").strip() or os.getenv("RAILWAY_ENVIRONMENT"):
        return
    log.warning(
        "⚠️   BACKEND_URL не задан. Пока файлы лежат в UPLOAD_DIR, это ни на "
        "что не влияет; но если файла там не окажется, забрать его будет "
        "неоткуда. Укажите внешний адрес приложения."
    )


# Локально миграции удобно катить при старте; на Railway их двигает
# preDeployCommand, и приложение обязано только проверить, что схема доехала.
MIGRATE_ON_STARTUP = os.getenv("MIGRATE_ON_STARTUP", "1").strip().lower() not in (
    "0", "false", "no",
)


@app.on_event("startup")
def startup():
    if MIGRATE_ON_STARTUP:
        try:
            run_migrations()
        except Exception as e:
            log.error(f"❌  миграции не применились: {e}")
            raise
        try:
            seed_db()
        except Exception as e:
            log.error(f"❌  seed_db() FAILED: {e}")
            raise
    else:
        ok, message = schema_is_current()
        log.error(("🗄️   " if ok else "❌  ") + message)
        if not ok:
            # Обслуживать запросы на отставшей схеме — это 500-е в рантайме
            # у пользователей вместо честного отказа подняться.
            raise RuntimeError(message)
    try:
        encrypt_existing_secrets()
    except Exception as e:
        log.error(f"❌  не удалось зашифровать токены интеграций: {e}")
        raise
    check_public_url()
    check_ai_model()
    try:
        check_upload_storage()
    except Exception as e:
        log.error(f"❌  проблема с каталогом загрузок: {e}")
        raise
    try:
        check_time_alignment()
    except Exception as e:
        log.warning(f"⚠️   не удалось сверить время базы и приложения: {e}")
    try:
        ensure_admin_exists()
    except Exception as e:
        log.warning(f"⚠️   не удалось проверить наличие администратора: {e}")
    scheduler.start(app)
    log.info("✅  MediaHub API запущен!  →  http://localhost:8000")


@app.get("/uploads/{filename}")
def serve_upload(filename: str, exp: str | None = None, sig: str | None = None):
    """
    Раздача загрузок по подписанной ссылке.

    Раньше здесь стоял StaticFiles без единой проверки: кто знал URL, тот
    скачивал файл, и медиа закрытых групп были фактически публичны. Заголовок
    авторизации к <img src="..."> не приложить, поэтому право доступа несёт
    подпись в самой ссылке — её выдаёт API тому, кто уже видит содержащую
    запись, и живёт она ограниченное время.
    """
    if not UPLOAD_NAME_RE.match(filename):
        raise HTTPException(404, "Файл не найден")
    check_upload_signature(filename, exp, sig)

    path = os.path.realpath(os.path.join(UPLOAD_DIR, filename))
    # Подпись считается по имени, но выход за каталог проверяем всё равно:
    # одна ошибка в регулярке не должна открывать файловую систему.
    if not path.startswith(os.path.realpath(UPLOAD_DIR) + os.sep) or not os.path.isfile(path):
        raise HTTPException(404, "Файл не найден")

    # Тип содержимого называем сами, а не отдаём на угадывание по расширению.
    # Незнакомое расширение — поток байтов вложением: файлы, легшие на диск до
    # того, как расширение стали выводить из типа, могут называться как угодно,
    # и веб-страница среди них выполнялась бы прямо на нашем домене.
    media_type, inline = serve_disposition(filename)
    headers = {"X-Content-Type-Options": "nosniff"}
    if not inline:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return FileResponse(path, media_type=media_type, headers=headers)
