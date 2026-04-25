"""
MediaHub — Медиахаб для молодёжных центров
FastAPI + PostgreSQL backend
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
import psycopg2.extras
import json, os, random
from datetime import datetime, timedelta
from dotenv import load_dotenv

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

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mediahub:mediahub123@localhost:5432/mediahub")

# ── Pydantic models ──────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    title: str
    content: str
    status: str = "draft"
    platforms: List[str] = ["vk"]
    tags: List[str] = []
    scheduled_at: Optional[str] = None
    template_type: Optional[str] = None
    author_id: int = 1

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    platforms: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    scheduled_at: Optional[str] = None

class GenerateRequest(BaseModel):
    template_type: str
    fields: dict

class UserUpdate(BaseModel):
    role: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for key in ("platforms", "tags"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = []
    return d

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

    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()["count"] == 0:
        c.executemany(
            "INSERT INTO users (name, email, role, avatar) VALUES (%s, %s, %s, %s)",
            [
                ("Алексей Иванов",  "admin@mediahub.ru",    "admin",    "АИ"),
                ("Мария Петрова",   "editor@mediahub.ru",   "editor",   "МП"),
                ("Дмитрий Сидоров", "observer@mediahub.ru", "observer", "ДС"),
            ],
        )

    c.execute("SELECT COUNT(*) FROM templates")
    if c.fetchone()["count"] == 0:
        c.executemany(
            "INSERT INTO templates (name, type, description, fields, template_text) VALUES (%s, %s, %s, %s, %s)",
            [
                ("Анонс мероприятия", "announcement", "Объявление о предстоящем событии",
                 json.dumps([
                     {"key": "event_name",   "label": "Название мероприятия", "placeholder": "Хакатон «IT-Кубок»"},
                     {"key": "date",         "label": "Дата и время",         "placeholder": "25 апреля, 10:00"},
                     {"key": "location",     "label": "Место проведения",     "placeholder": "МЦ «Зеркало»"},
                     {"key": "description",  "label": "Краткое описание",     "placeholder": "Соревнования по программированию"},
                     {"key": "contact",      "label": "Контакт для записи",   "placeholder": "@smm_manager"},
                 ]),
                 "🔥 {event_name}\n\n📅 Дата: {date}\n📍 Место: {location}\n\n{description}\n\n👉 Успей зарегистрироваться! Контакт: {contact}\n\n#мероприятие #молодёжь #красноярск"),
                ("Итоги события", "results", "Публикация результатов прошедшего мероприятия",
                 json.dumps([
                     {"key": "event_name",    "label": "Название мероприятия",   "placeholder": "Форум молодых лидеров"},
                     {"key": "participants",  "label": "Кол-во участников",       "placeholder": "150"},
                     {"key": "highlights",    "label": "Главные моменты",         "placeholder": "5 спикеров, мастер-классы"},
                     {"key": "next_event",    "label": "Следующее мероприятие",   "placeholder": "Следующий форум — в июне"},
                 ]),
                 "✅ {event_name} — позади!\n\n👥 Участников: {participants}\n\n🎯 {highlights}\n\nСпасибо всем! {next_event} — следите за анонсами.\n\n#итоги #молодёжь #красноярск"),
                ("Вакансия", "vacancy", "Объявление об открытой позиции",
                 json.dumps([
                     {"key": "position",     "label": "Должность",    "placeholder": "SMM-менеджер"},
                     {"key": "organization", "label": "Организация",  "placeholder": "МЦ «Зеркало»"},
                     {"key": "requirements", "label": "Требования",   "placeholder": "Опыт от 1 года"},
                     {"key": "conditions",   "label": "Условия",      "placeholder": "Гибкий график"},
                     {"key": "contact",      "label": "Контакт",      "placeholder": "@hr_manager"},
                 ]),
                 "🚀 Вакансия: {position}\n🏢 {organization}\n\n📋 Требования:\n{requirements}\n\n💼 Условия:\n{conditions}\n\n📩 Откликнуться: {contact}\n\n#вакансия #работа #красноярск"),
                ("Грант", "grant", "Информация о грантовой программе",
                 json.dumps([
                     {"key": "grant_name", "label": "Название гранта",  "placeholder": "Грант «Молодёжь края»"},
                     {"key": "amount",     "label": "Размер поддержки", "placeholder": "до 500 000 ₽"},
                     {"key": "deadline",   "label": "Дедлайн подачи",   "placeholder": "1 мая 2026"},
                     {"key": "who",        "label": "Для кого",         "placeholder": "НКО и молодёжные орг."},
                     {"key": "link",       "label": "Ссылка",           "placeholder": "grant.krasn.ru"},
                 ]),
                 "💰 {grant_name}\n\n🎁 Поддержка: {amount}\n⏰ Дедлайн: {deadline}\n\n👥 Для кого: {who}\n\n🔗 Подробнее: {link}\n\n#грант #поддержка #молодёжь"),
            ],
        )

    c.execute("SELECT COUNT(*) FROM posts")
    if c.fetchone()["count"] == 0:
        now = datetime.now()
        rows = [
            ("🔥 Хакатон IT-Кубок — регистрация открыта!",
             "🔥 Хакатон IT-Кубок\n\n📅 Дата: 25–26 апреля, 10:00\n📍 Место: Каменка\n\nСоревнования по программированию.\n\n👉 @it_kubok\n\n#мероприятие #молодёжь",
             "published", ["vk", "telegram"], ["мероприятия"], -7, 1850, 142, 38, 24, "announcement"),
            ("✅ Форум молодых лидеров — итоги!",
             "✅ Форум молодых лидеров — позади!\n\n👥 Участников: 200\n\n🎯 7 спикеров, 4 мастер-класса.\n\n#итоги #молодёжь",
             "published", ["vk"], ["мероприятия"], -14, 2100, 198, 55, 41, "results"),
            ("🚀 Вакансия: SMM-менеджер в МЦ «Зеркало»",
             "🚀 SMM-менеджер\n🏢 МЦ «Зеркало»\n\n📋 Опыт от 1 года\n💼 Гибкий график\n📩 @hr_zerkalo\n\n#вакансия",
             "published", ["vk", "telegram"], ["вакансии"], -5, 980, 64, 12, 8, "vacancy"),
            ("💰 Грант «Молодёжь края» — подай заявку",
             "💰 Грант «Молодёжь края»\n\n🎁 до 500 000 ₽\n⏰ 1 мая 2026\n🔗 grant.krasn.ru\n\n#грант",
             "published", ["vk"], ["гранты"], -3, 1340, 87, 21, 15, "grant"),
            ("🌟 Волонтёрская смена — набор участников",
             "🌟 Волонтёрская смена 2026\n\n📅 1–7 июня\n📍 Столбы\n\n#волонтёр",
             "scheduled", ["vk", "telegram"], ["мероприятия"], 2, 0, 0, 0, 0, "announcement"),
            ("📊 Итоги апреля — наша статистика",
             "📊 Апрель:\n\n✅ 24 публикации\n👥 Охват: 1 200\n❤️ Вовлечённость: 8.3%\n\n#статистика",
             "scheduled", ["vk"], ["новости"], 1, 0, 0, 0, 0, None),
            ("🎓 Интенсив «Стартап за 48 часов»",
             "🎓 Интенсив «Стартап за 48 часов»\n\n📅 10 мая\n📍 Краевой дворец молодёжи\n\n#стартап",
             "draft", ["vk", "telegram"], ["мероприятия"], 5, 0, 0, 0, 0, "announcement"),
            ("🏋️ Спортивный фестиваль «Активная молодёжь»",
             "🏋️ «Активная молодёжь»\n\n📅 18 мая\n📍 Стадион «Рассвет»\n\n#спорт",
             "draft", ["vk"], ["мероприятия"], 10, 0, 0, 0, 0, None),
        ]
        for title, content, status, platforms, tags, days, views, reactions, comments, shares, tmpl in rows:
            dt = now + timedelta(days=days)
            scheduled_at = dt.strftime("%Y-%m-%dT%H:%M") if status == "scheduled" else None
            published_at  = dt.strftime("%Y-%m-%dT%H:%M") if status == "published"  else None
            created_at    = (now + timedelta(days=days - 1)).strftime("%Y-%m-%dT%H:%M")
            c.execute(
                "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,published_at,views,reactions,comments,shares,author_id,template_type,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (title, content, status, json.dumps(platforms), json.dumps(tags), scheduled_at, published_at, views, reactions, comments, shares, random.choice([1, 2]), tmpl, created_at),
            )

        c.executemany(
            "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, %s)",
            [
                (1, "Пост «Хакатон IT-Кубок» опубликован",          "success", 0),
                (1, "Запланирован пост на завтра: «Итоги апреля»",  "info",    0),
                (1, "Черновик «Спортивный фестиваль» не опубликован 5 дней", "warning", 1),
                (2, "Новый пост на модерации от волонтёра",          "info",    0),
            ],
        )

    conn.commit()
    conn.close()

# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "MediaHub API"}

# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=%s", (req.email,))
    user = c.fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "Неверный email")
    return {"user": row_to_dict(user), "token": "demo-token"}

# ── Users ────────────────────────────────────────────────────────────────────

@app.get("/api/users")
def get_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

@app.put("/api/users/{user_id}/role")
def update_role(user_id: int, body: UserUpdate):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET role=%s WHERE id=%s", (body.role, user_id))
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = c.fetchone()
    conn.close()
    return row_to_dict(user)

# ── Posts ────────────────────────────────────────────────────────────────────

@app.get("/api/posts")
def get_posts(status: Optional[str] = None, platform: Optional[str] = None, tag: Optional[str] = None, limit: int = 100, offset: int = 0):
    conn = get_db()
    c = conn.cursor()
    q = "SELECT p.*, u.name as author_name FROM posts p LEFT JOIN users u ON p.author_id=u.id WHERE 1=1"
    params: list = []
    if status:
        q += " AND p.status=%s";   params.append(status)
    if platform:
        q += " AND p.platforms LIKE %s"; params.append(f'%"{platform}"%')
    if tag:
        q += " AND p.tags LIKE %s";      params.append(f'%"{tag}"%')
    q += " ORDER BY p.created_at DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    c.execute(q, params)
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM posts")
    total = c.fetchone()["count"]
    conn.close()
    return {"posts": [row_to_dict(r) for r in rows], "total": total}

@app.get("/api/posts/{post_id}")
def get_post(post_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT p.*, u.name as author_name FROM posts p LEFT JOIN users u ON p.author_id=u.id WHERE p.id=%s", (post_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Пост не найден")
    return row_to_dict(row)

@app.post("/api/posts")
def create_post(body: PostCreate):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,author_id,template_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (body.title, body.content, body.status, json.dumps(body.platforms), json.dumps(body.tags), body.scheduled_at, body.author_id, body.template_type),
    )
    pid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    row = c.fetchone()
    conn.close()
    return row_to_dict(row)

@app.put("/api/posts/{post_id}")
def update_post(post_id: int, body: PostUpdate):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM posts WHERE id=%s", (post_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Пост не найден")
    updates, params = [], []
    if body.title      is not None: updates.append("title=%s");        params.append(body.title)
    if body.content    is not None: updates.append("content=%s");      params.append(body.content)
    if body.status     is not None: updates.append("status=%s");       params.append(body.status)
    if body.platforms  is not None: updates.append("platforms=%s");    params.append(json.dumps(body.platforms))
    if body.tags       is not None: updates.append("tags=%s");         params.append(json.dumps(body.tags))
    if body.scheduled_at is not None: updates.append("scheduled_at=%s"); params.append(body.scheduled_at)
    if updates:
        params.append(post_id)
        c.execute(f"UPDATE posts SET {', '.join(updates)} WHERE id=%s", params)
        conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    conn.close()
    return row_to_dict(row)

@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM posts WHERE id=%s", (post_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404)
    c.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/posts/{post_id}/publish")
def publish_post(post_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM posts WHERE id=%s", (post_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute(
        "UPDATE posts SET status='published',published_at=%s,views=%s,reactions=%s,comments=%s,shares=%s WHERE id=%s",
        (now, random.randint(300, 1500), random.randint(20, 120), random.randint(5, 40), random.randint(3, 25), post_id),
    )
    conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    conn.close()
    return row_to_dict(row)

# ── Calendar ─────────────────────────────────────────────────────────────────

@app.get("/api/calendar")
def get_calendar(start: str = Query(...), end: str = Query(...)):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id,title,status,platforms,tags,scheduled_at,published_at,created_at FROM posts "
        "WHERE (scheduled_at BETWEEN %s AND %s) OR (published_at BETWEEN %s AND %s) OR (created_at BETWEEN %s AND %s) "
        "ORDER BY COALESCE(scheduled_at, published_at, created_at)",
        (start, end, start, end, start, end),
    )
    rows = c.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

# ── Templates ─────────────────────────────────────────────────────────────────

@app.get("/api/templates")
def get_templates():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM templates")
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["fields"] = json.loads(d["fields"])
        except Exception:
            d["fields"] = []
        result.append(d)
    return result

@app.post("/api/generate-text")
def generate_text(body: GenerateRequest):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM templates WHERE type=%s", (body.template_type,))
    tmpl = c.fetchone()
    conn.close()
    if not tmpl:
        raise HTTPException(404, "Шаблон не найден")
    text = tmpl["template_text"]
    for k, v in body.fields.items():
        text = text.replace(f"{{{k}}}", v)
    titles = {
        "announcement": "Анонс: " + body.fields.get("event_name", ""),
        "results":      "Итоги: " + body.fields.get("event_name", ""),
        "vacancy":      "Вакансия: " + body.fields.get("position", ""),
        "grant":        body.fields.get("grant_name", ""),
    }
    return {"text": text, "title": titles.get(body.template_type, "Новый пост")}

# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/api/analytics/summary")
def analytics_summary():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM posts");                         total     = c.fetchone()["count"]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='published'"); published = c.fetchone()["count"]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='scheduled'"); scheduled = c.fetchone()["count"]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='draft'");     drafts    = c.fetchone()["count"]
    c.execute("SELECT SUM(views) v,SUM(reactions) r,SUM(comments) c,SUM(shares) sh FROM posts WHERE status='published'")
    s = c.fetchone()
    c.execute(
        "SELECT id,title,views,reactions,comments,shares,published_at FROM posts "
        "WHERE status='published' ORDER BY (views+reactions*3+comments*2+shares*4) DESC LIMIT 5"
    )
    top = c.fetchall()
    pl_stats = []
    for pl in ["vk", "telegram"]:
        c.execute(
            "SELECT COUNT(*) cnt,SUM(views) v,SUM(reactions) r FROM posts "
            "WHERE platforms LIKE %s AND status='published'",
            (f'%"{pl}"%',),
        )
        ps = c.fetchone()
        pl_stats.append({"platform": pl, "count": ps["cnt"] or 0, "views": ps["v"] or 0, "reactions": ps["r"] or 0})
    conn.close()
    total_views = s["v"] or 0
    eng = round(((s["r"] or 0) + (s["c"] or 0)) / max(total_views, 1) * 100, 1)
    return {
        "total_posts": total, "published": published, "scheduled": scheduled, "drafts": drafts,
        "total_views": total_views, "total_reactions": s["r"] or 0,
        "total_comments": s["c"] or 0, "total_shares": s["sh"] or 0,
        "avg_views": round(total_views / max(published, 1)),
        "engagement_rate": eng,
        "top_posts": [dict(r) for r in top],
        "platform_stats": pl_stats,
    }

@app.get("/api/analytics/timeline")
def analytics_timeline(period: str = "month"):
    days = {"week": 7, "month": 30, "quarter": 90}.get(period, 30)
    now = datetime.now()
    result = []
    conn = get_db()
    c = conn.cursor()
    for i in range(days - 1, -1, -1):
        day = now - timedelta(days=i)
        ds = day.strftime("%Y-%m-%d")
        c.execute(
            "SELECT SUM(views) v, SUM(reactions) r, COUNT(*) p FROM posts WHERE published_at LIKE %s",
            (ds + "%",),
        )
        row = c.fetchone()
        result.append({"date": ds, "label": day.strftime("%d.%m"), "views": row["v"] or 0, "reactions": row["r"] or 0, "posts": row["p"] or 0})
    conn.close()
    return result

# ── Notifications ─────────────────────────────────────────────────────────────

@app.get("/api/notifications")
def get_notifications(user_id: int = 1):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.put("/api/notifications/{notif_id}/read")
def mark_read(notif_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE id=%s", (notif_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()
    print("✅  MediaHub API запущен!  →  http://localhost:8000")
