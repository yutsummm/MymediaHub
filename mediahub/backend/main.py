"""
MediaHub — Медиахаб для молодёжных центров
FastAPI + PostgreSQL backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os, json, random, datetime, hashlib

from utils import get_db, hash_password, UPLOAD_DIR

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

from routers.auth import router as auth_router
from routers.posts import router as posts_router
from routers.groups import router as groups_router
from routers.settings import router as settings_router
from routers.volunteer_media import router as volunteer_media_router
from routers.notifications import router as notifications_router
from routers.analytics import router as analytics_router
from routers.users import router as users_router
from routers.yc import router as yc_router
from routers.upload import router as upload_router

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


# ── DB init ──────────────────────────────────────────────────────────────────

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL DEFAULT 'editor',
            avatar TEXT DEFAULT '',
            created_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            platforms TEXT DEFAULT '["vk"]',
            tags TEXT DEFAULT '[]',
            scheduled_at TEXT,
            published_at TEXT,
            views INTEGER DEFAULT 0,
            reactions INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            author_id INTEGER DEFAULT 1,
            template_type TEXT,
            created_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI'),
            FOREIGN KEY (author_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL UNIQUE,
            description TEXT,
            fields TEXT DEFAULT '[]',
            template_text TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER DEFAULT 1,
            message TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vk_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            group_id TEXT NOT NULL,
            access_token TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            connected_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tg_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            bot_token TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            chat_title TEXT DEFAULT '',
            connected_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS media TEXT DEFAULT '[]'")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS location_address TEXT")
    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS location_lat DOUBLE PRECISION")
    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS location_lng DOUBLE PRECISION")

    c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            avatar TEXT DEFAULT '',
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id SERIAL PRIMARY KEY,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'editor',
            joined_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI'),
            UNIQUE (group_id, user_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS invite_links (
            id SERIAL PRIMARY KEY,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'editor',
            created_by INTEGER NOT NULL REFERENCES users(id),
            expires_at TEXT NOT NULL,
            used_count INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            created_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_media (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            event_name TEXT NOT NULL,
            media TEXT DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id)")
    c.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id)")
    c.execute("ALTER TABLE vk_settings ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES groups(id)")
    c.execute("ALTER TABLE tg_settings ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES groups(id)")
    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS vk_post_id TEXT")
    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS tg_message_ids TEXT DEFAULT '[]'")
    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS vk_stats_updated_at TEXT")

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
        now = datetime.datetime.now()
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


@app.on_event("startup")
def startup():
    try:
        init_db()
        print("✅  MediaHub API запущен!  →  http://localhost:8000")
    except Exception as e:
        print(f"❌  init_db() FAILED: {e}")
        raise


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
