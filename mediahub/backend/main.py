"""
MediaHub — Медиахаб для молодёжных центров
FastAPI + PostgreSQL backend
"""

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
import psycopg2.extras
import json, os, random, uuid, shutil, hashlib
import requests as http_requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="MediaHub API", version="1.0.0")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
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

# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# ── Pydantic models ──────────────────────────────────────────────────────────

class MediaItem(BaseModel):
    url: str
    type: str      # "image" | "video"
    filename: str

class PostCreate(BaseModel):
    title: str
    content: str
    status: str = "draft"
    platforms: List[str] = ["vk"]
    tags: List[str] = []
    scheduled_at: Optional[str] = None
    template_type: Optional[str] = None
    author_id: int = 1
    media: List[MediaItem] = []

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    platforms: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    scheduled_at: Optional[str] = None
    media: Optional[List[MediaItem]] = None

class GenerateRequest(BaseModel):
    template_type: str
    fields: dict

class UserUpdate(BaseModel):
    role: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AIEnhanceRequest(BaseModel):
    text: str
    mode: str  # 'creative' | 'russify'

class VkSettingsSave(BaseModel):
    group_id: str
    access_token: str

class VkOAuthExchange(BaseModel):
    app_id: str
    app_secret: str
    code: str
    group_id: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class UserCreate(BaseModel):
    name: str
    email: str
    role: str = "editor"
    password: str

# ── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    for key in ("platforms", "tags", "media"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = []
        elif key not in d:
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS vk_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            group_id TEXT NOT NULL,
            access_token TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            connected_at TEXT DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD"T"HH24:MI')
        )
    """)

    c.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS media TEXT DEFAULT '[]'")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")

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

# ── File upload ──────────────────────────────────────────────────────────────

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-msvideo"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES:
        raise HTTPException(400, f"Неподдерживаемый тип файла: {content_type}")

    ext = (file.filename or "file").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    data = await file.read()
    max_size = MAX_VIDEO_SIZE if content_type in ALLOWED_VIDEO_TYPES else MAX_IMAGE_SIZE
    if len(data) > max_size:
        raise HTTPException(400, f"Файл слишком большой (макс. {max_size // 1024 // 1024} МБ)")

    with open(filepath, "wb") as f:
        f.write(data)

    file_type = "video" if content_type in ALLOWED_VIDEO_TYPES else "image"
    return {"url": f"/uploads/{filename}", "type": file_type, "filename": file.filename or filename}

# ── AI Enhance ───────────────────────────────────────────────────────────────

_AI_PROMPTS = {
    "creative": (
        "Ты — опытный SMM-специалист и копирайтер молодёжного медиацентра. "
        "Перепиши текст поста: сделай его ярким, цепляющим и живым для молодёжной аудитории. "
        "Сохрани основной смысл и все ключевые факты (даты, места, имена, цифры). "
        "Используй эмодзи там, где это уместно. "
        "Верни ТОЛЬКО готовый текст — без пояснений, без кавычек, без предисловий."
    ),
    "russify": (
        "Ты — редактор русского языка. "
        "Замени все англицизмы, иностранный сленг и заимствованные слова на естественные русские аналоги, "
        "которые органично вписываются в контекст и не режут слух. "
        "Не меняй смысл, тон и структуру текста. Все факты, даты, имена и эмодзи оставь без изменений. "
        "Верни ТОЛЬКО готовый текст — без пояснений, без кавычек, без предисловий."
    ),
}

@app.post("/api/ai-enhance")
def ai_enhance(body: AIEnhanceRequest):
    if not body.text.strip():
        raise HTTPException(400, "Текст не может быть пустым")

    system_prompt = _AI_PROMPTS.get(body.mode)
    if not system_prompt:
        raise HTTPException(400, "Неверный режим. Допустимые значения: creative, russify")

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(503, (
            "GROQ_API_KEY не настроен. "
            "Получите бесплатный ключ на console.groq.com и добавьте его в .env"
        ))

    try:
        resp = http_requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body.text},
                ],
                "temperature": 0.75 if body.mode == "creative" else 0.25,
                "max_tokens": 2000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        enhanced = result["choices"][0]["message"]["content"].strip()
        return {"text": enhanced}
    except http_requests.exceptions.Timeout:
        raise HTTPException(504, "Превышено время ожидания ответа от ИИ (30 с)")
    except http_requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        raise HTTPException(502, f"Ошибка Groq API: {detail or str(e)}")
    except http_requests.exceptions.RequestException as e:
        raise HTTPException(502, f"Ошибка связи с ИИ: {str(e)}")
    except (KeyError, IndexError):
        raise HTTPException(502, "Неожиданный формат ответа от ИИ")

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
        # API v5.196+ returns {"groups": [...]}; older versions return [...]
        if isinstance(response, list):
            groups = response
        else:
            groups = response.get("groups", [])
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

def vk_wall_post(access_token: str, group_id: str, message: str, attachments: List[str] = []) -> int:
    clean_id = group_id.lstrip("-")
    params: dict = {"owner_id": f"-{clean_id}", "message": message, "access_token": access_token, "v": VK_API_VERSION}
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

# ── VK Settings ───────────────────────────────────────────────────────────────

@app.get("/api/settings/vk")
def get_vk_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, group_id, group_name, connected_at FROM vk_settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    d = dict(row)
    d["connected"] = True
    return d

@app.post("/api/settings/vk")
def save_vk_settings(body: VkSettingsSave):
    try:
        group_name = vk_get_group_name(body.access_token, body.group_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM vk_settings WHERE id=1")
    exists = c.fetchone()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if exists:
        c.execute(
            "UPDATE vk_settings SET group_id=%s, access_token=%s, group_name=%s, connected_at=%s WHERE id=1",
            (body.group_id.lstrip("-"), body.access_token, group_name, now),
        )
    else:
        c.execute(
            "INSERT INTO vk_settings (id, group_id, access_token, group_name, connected_at) VALUES (1, %s, %s, %s, %s)",
            (body.group_id.lstrip("-"), body.access_token, group_name, now),
        )
    conn.commit()
    conn.close()
    return {"connected": True, "group_id": body.group_id.lstrip("-"), "group_name": group_name, "connected_at": now}

@app.post("/api/vk/oauth-exchange")
def vk_oauth_exchange(body: VkOAuthExchange):
    r = http_requests.get(
        "https://oauth.vk.com/access_token",
        params={
            "client_id": body.app_id,
            "client_secret": body.app_secret,
            "redirect_uri": "https://oauth.vk.com/blank.html",
            "code": body.code,
        },
        timeout=10,
    )
    data = r.json()
    if "error" in data:
        raise HTTPException(400, data.get("error_description") or data.get("error", "OAuth ошибка"))
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(400, "Токен не получен от VK")
    try:
        group_name = vk_get_group_name(access_token, body.group_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM vk_settings WHERE id=1")
    exists = c.fetchone()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    clean_id = body.group_id.lstrip("-")
    if exists:
        c.execute(
            "UPDATE vk_settings SET group_id=%s, access_token=%s, group_name=%s, connected_at=%s WHERE id=1",
            (clean_id, access_token, group_name, now),
        )
    else:
        c.execute(
            "INSERT INTO vk_settings (id, group_id, access_token, group_name, connected_at) VALUES (1, %s, %s, %s, %s)",
            (clean_id, access_token, group_name, now),
        )
    conn.commit()
    conn.close()
    return {"connected": True, "group_id": clean_id, "group_name": group_name, "connected_at": now}

@app.delete("/api/settings/vk")
def delete_vk_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM vk_settings WHERE id=1")
    conn.commit()
    conn.close()
    return {"connected": False}

# ── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=%s", (req.email,))
    user = c.fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    ph = user.get("password_hash")
    if ph and not verify_password(req.password, ph):
        raise HTTPException(401, "Неверный пароль")
    return {"user": row_to_dict(user), "token": "demo-token"}

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    if not req.name.strip():
        raise HTTPException(400, "Введите имя")
    if not req.email.strip():
        raise HTTPException(400, "Введите email")
    if len(req.password) < 6:
        raise HTTPException(400, "Пароль должен содержать минимум 6 символов")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=%s", (req.email.lower().strip(),))
    if c.fetchone():
        conn.close()
        raise HTTPException(409, "Пользователь с таким email уже существует")
    avatar = "".join(p[0].upper() for p in req.name.strip().split()[:2])
    c.execute(
        "INSERT INTO users (name, email, role, avatar, password_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (req.name.strip(), req.email.lower().strip(), "editor", avatar, hash_password(req.password)),
    )
    uid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = c.fetchone()
    conn.close()
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

@app.post("/api/users")
def create_user(body: UserCreate):
    if not body.name.strip():
        raise HTTPException(400, "Введите имя")
    if not body.email.strip():
        raise HTTPException(400, "Введите email")
    if len(body.password) < 6:
        raise HTTPException(400, "Пароль должен содержать минимум 6 символов")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=%s", (body.email.lower().strip(),))
    if c.fetchone():
        conn.close()
        raise HTTPException(409, "Пользователь с таким email уже существует")
    avatar = "".join(p[0].upper() for p in body.name.strip().split()[:2])
    c.execute(
        "INSERT INTO users (name, email, role, avatar, password_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (body.name.strip(), body.email.lower().strip(), body.role, avatar, hash_password(body.password)),
    )
    uid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = c.fetchone()
    conn.close()
    return row_to_dict(user)

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=%s", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Пользователь не найден")
    c.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

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
        "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,author_id,template_type,media) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (body.title, body.content, body.status, json.dumps(body.platforms), json.dumps(body.tags), body.scheduled_at, body.author_id, body.template_type, json.dumps([m.dict() for m in body.media])),
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
    if body.media      is not None: updates.append("media=%s");        params.append(json.dumps([m.dict() for m in body.media]))
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
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    post = c.fetchone()
    if not post:
        conn.close()
        raise HTTPException(404)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute(
        "UPDATE posts SET status='published',published_at=%s,views=%s,reactions=%s,comments=%s,shares=%s WHERE id=%s",
        (now, random.randint(300, 1500), random.randint(20, 120), random.randint(5, 40), random.randint(3, 25), post_id),
    )
    conn.commit()

    post_dict = row_to_dict(post)
    vk_post_id = None
    vk_error = None
    photo_errors: list = []

    platforms = post_dict.get("platforms", [])
    if "vk" in platforms:
        c.execute("SELECT group_id, access_token FROM vk_settings WHERE id=1")
        vk = c.fetchone()
        if vk:
            try:
                message = f"{post_dict['title']}\n\n{post_dict['content']}"
                attachments = []
                backend_base = os.getenv("BACKEND_URL", "https://backend-production-30d6.up.railway.app").rstrip("/")
                for item in (post_dict.get("media") or []):
                    if item.get("type") == "image":
                        fname = os.path.basename(item["url"])
                        fpath = os.path.join(UPLOAD_DIR, fname)
                        try:
                            if os.path.exists(fpath):
                                with open(fpath, "rb") as f:
                                    image_data = f.read()
                            else:
                                img_url = f"{backend_base}{item['url']}"
                                resp = http_requests.get(img_url, timeout=30)
                                resp.raise_for_status()
                                image_data = resp.content
                            att = vk_upload_photo_to_wall(vk["access_token"], vk["group_id"], image_data, fname)
                            attachments.append(att)
                        except Exception as photo_err:
                            msg = str(photo_err)
                            if any(kw in msg.lower() for kw in [
                                "unavailable with group auth",
                                "group authorization",
                                "access denied",
                                "this action is not available",
                                "community token",
                                "group token",
                                "error_code: 15",
                            ]):
                                msg = "Токен группы не поддерживает загрузку фото. Для публикации фото подключите VK через OAuth (✨ OAuth вкладка в Настройках)"
                            photo_errors.append(msg)
                vk_post_id = vk_wall_post(vk["access_token"], vk["group_id"], message, attachments)
                if photo_errors:
                    notif_msg = (
                        f"Пост «{post_dict['title']}» опубликован в ВКонтакте, "
                        f"но {len(photo_errors)} фото не загружено: {photo_errors[0]}"
                    )
                    notif_type = "warning"
                else:
                    notif_msg = f"Пост «{post_dict['title']}» опубликован в группу ВКонтакте"
                    notif_type = "success"
                c.execute(
                    "INSERT INTO notifications (user_id, message, type, is_read) VALUES (1, %s, %s, 0)",
                    (notif_msg, notif_type),
                )
                conn.commit()
            except Exception as e:
                vk_error = str(e)
                c.execute(
                    "INSERT INTO notifications (user_id, message, type, is_read) VALUES (1, %s, %s, 0)",
                    (f"Ошибка публикации в VK: {vk_error}", "error"),
                )
                conn.commit()

    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    conn.close()
    result = row_to_dict(row)
    if vk_post_id is not None:
        result["vk_post_id"] = vk_post_id
    if vk_error is not None:
        result["vk_error"] = vk_error
    if photo_errors:
        result["vk_photo_errors"] = photo_errors
    return result

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

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
