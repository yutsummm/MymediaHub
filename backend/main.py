"""
MediaHub — Медиахаб для молодёжных центров
FastAPI + PostgreSQL backend
"""

import datetime
import json
import os
import random

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import scheduler
from alembic import command
from alembic.config import Config
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
    encrypt_secret,
    get_db,
    hash_password,
)

load_dotenv()

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


# ── Routers ──────────────────────────────────────────────────────────────────

from routers.analytics import router as analytics_router
from routers.auth import router as auth_router
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
app.include_router(users_router)
app.include_router(yc_router)
app.include_router(upload_router)


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "MediaHub API"}


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


def run_migrations():
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
        print(f"alembic: существующая схема помечена ревизией {BASELINE_REVISION}")
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
                ("Мария Петрова", "editor@mediahub.ru", "editor", "МП", hash_password("editor123!")),
                ("Екатерина Волонтёр", "volunteer@mediahub.ru", "volunteer", "ЕВ", hash_password("volunteer123!")),
            ],
        )

    c.execute("SELECT COUNT(*) FROM templates")
    if c.fetchone()["count"] == 0:
        c.executemany(
            "INSERT INTO templates (name, type, description, fields, template_text) VALUES (%s, %s, %s, %s, %s)",
            [
                ("Анонс мероприятия", "announcement", "Объявление о предстоящем событии",
                 json.dumps([
                     {"key": "event_name", "label": "Название мероприятия", "placeholder": "Хакатон «IT-Кубок»"},
                     {"key": "date", "label": "Дата и время", "placeholder": "25 апреля, 10:00"},
                     {"key": "location", "label": "Место проведения", "placeholder": "МЦ «Зеркало»"},
                     {"key": "description", "label": "Краткое описание", "placeholder": "Соревнования по программированию"},
                     {"key": "contact", "label": "Контакт для записи", "placeholder": "@smm_manager"},
                 ]),
                 "🔥 {event_name}\n\n📅 Дата: {date}\n📍 Место: {location}\n\n{description}\n\n👉 Успей зарегистрироваться! Контакт: {contact}\n\n#мероприятие #молодёжь #красноярск"),
                ("Итоги события", "results", "Публикация результатов прошедшего мероприятия",
                 json.dumps([
                     {"key": "event_name", "label": "Название мероприятия", "placeholder": "Форум молодых лидеров"},
                     {"key": "participants", "label": "Кол-во участников", "placeholder": "150"},
                     {"key": "highlights", "label": "Главные моменты", "placeholder": "5 спикеров, мастер-классы"},
                     {"key": "next_event", "label": "Следующее мероприятие", "placeholder": "Следующий форум — в июне"},
                 ]),
                 "✅ {event_name} — позади!\n\n👥 Участников: {participants}\n\n🎯 {highlights}\n\nСпасибо всем! {next_event} — следите за анонсами.\n\n#итоги #молодёжь #красноярск"),
                ("Вакансия", "vacancy", "Объявление об открытой позиции",
                 json.dumps([
                     {"key": "position", "label": "Должность", "placeholder": "SMM-менеджер"},
                     {"key": "organization", "label": "Организация", "placeholder": "МЦ «Зеркало»"},
                     {"key": "requirements", "label": "Требования", "placeholder": "Опыт от 1 года"},
                     {"key": "conditions", "label": "Условия", "placeholder": "Гибкий график"},
                     {"key": "contact", "label": "Контакт", "placeholder": "@hr_manager"},
                 ]),
                 "🚀 Вакансия: {position}\n🏢 {organization}\n\n📋 Требования:\n{requirements}\n\n💼 Условия:\n{conditions}\n\n📩 Откликнуться: {contact}\n\n#вакансия #работа #красноярск"),
                ("Грант", "grant", "Информация о грантовой программе",
                 json.dumps([
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
                "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,published_at,views,reactions,comments,shares,author_id,template_type,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (title, content, status, json.dumps(platforms), json.dumps(tags),
                 scheduled_at, published_at, 0, 0, 0, 0, random.choice([1, 2]), tmpl, created_at),
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
        print(f"🔒  зашифровано токенов интеграций: {encrypted}")


def check_time_alignment() -> bool:
    """
    Сверяет часовой пояс базы и приложения.

    Даты-строки ставят двое: база через server_default (зона зашита миграцией)
    и код через app_now_str() (зона из APP_TZ). Если их развести, в одной
    колонке снова окажутся значения, различающиеся на несколько часов — ровно
    та беда, которую разбирала миграция e5c9d4a71b38. Проверка дешёвая, а
    заметить расхождение потом по данным очень трудно.

    Не роняет приложение: перекос по времени — повод для громкого предупреждения,
    но не для отказа обслуживать людей.
    """
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='posts' AND column_name='created_at'"
        )
        row = c.fetchone()
        expr = row and row.get("column_default")
        if not expr:
            return True
        c.execute(f"SELECT {expr} AS db_now")  # noqa: S608 — выражение из схемы, не из ввода
        db_now = c.fetchone()["db_now"]
    finally:
        conn.close()

    fmt = "%Y-%m-%dT%H:%M"
    drift = abs(
        (datetime.datetime.strptime(db_now, fmt)
         - datetime.datetime.strptime(app_now_str(), fmt)).total_seconds()
    ) / 60
    if drift > 5:
        print(
            f"⚠️   база и приложение расходятся во времени на {drift:.0f} мин: "
            f"база пишет {db_now}, приложение считает {app_now_str()}. "
            f"Проверьте APP_TZ (сейчас {APP_TZ}) и server_default дат — "
            "иначе в одной колонке снова окажутся разные часовые пояса."
        )
        return False
    print(f"🕒  время согласовано: {APP_TZ}, сейчас {db_now}")
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
        print(
            f"⚠️   загрузки: {UPLOAD_DIR} — каталог внутри контейнера. "
            "На Railway он пересоздаётся при каждой выкатке и файлы пропадут. "
            "Смонтируйте том и задайте UPLOAD_DIR."
        )
    else:
        print(f"📁  загрузки: {UPLOAD_DIR} (файлов: {len(files)})")


@app.on_event("startup")
def startup():
    try:
        run_migrations()
    except Exception as e:
        print(f"❌  миграции не применились: {e}")
        raise
    try:
        seed_db()
    except Exception as e:
        print(f"❌  seed_db() FAILED: {e}")
        raise
    try:
        encrypt_existing_secrets()
    except Exception as e:
        print(f"❌  не удалось зашифровать токены интеграций: {e}")
        raise
    try:
        check_upload_storage()
    except Exception as e:
        print(f"❌  проблема с каталогом загрузок: {e}")
        raise
    try:
        check_time_alignment()
    except Exception as e:
        print(f"⚠️   не удалось сверить время базы и приложения: {e}")
    scheduler.start(app)
    print("✅  MediaHub API запущен!  →  http://localhost:8000")


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
    return FileResponse(path)
