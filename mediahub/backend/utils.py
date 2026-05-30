"""
MediaHub — shared utilities and helpers
"""

from fastapi import HTTPException, Header
from typing import Optional, List
import psycopg2
import psycopg2.extras
import json, os, hashlib, bcrypt, uuid, time
from jose import jwt, JWTError
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from urllib.parse import quote
import requests as http_requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import secrets

# ── DB ───────────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mediahub:mediahub123@localhost:5432/mediahub")

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    for key in ("platforms", "tags", "media", "tg_message_ids"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = [] if key != "tg_message_ids" else []
        elif key not in d:
            d[key] = [] if key != "tg_message_ids" else []
    if "tg_message_ids" in d and not isinstance(d["tg_message_ids"], list):
        d["tg_message_ids"] = []
    return d


# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == hashed


# ── JWT helpers ──────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    print("WARNING: JWT_SECRET not set. Using a random key. Set JWT_SECRET in environment for persistence across restarts.")
JWT_ALGORITHM = "HS256"


def create_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=72)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user_id(authorization: str = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")
    try:
        token = authorization.split(" ", 1)[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError, IndexError):
        raise HTTPException(401, "Недействительный токен")


# ── Rate limiter ────────────────────────────────────────────────────────────

RATE_LIMIT_STORE: dict[str, list[float]] = {}


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60):
    now = time.time()
    entry = RATE_LIMIT_STORE.get(key, [])
    entry = [t for t in entry if now - t < window_seconds]
    if len(entry) >= max_requests:
        raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")
    entry.append(now)
    RATE_LIMIT_STORE[key] = entry


# ── Email ────────────────────────────────────────────────────────────────────

def send_reset_email(to_email: str, code: str):
    api_key = os.getenv("BREVO_API_KEY", "")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "")
    sender_name = os.getenv("BREVO_SENDER_NAME", "MediaHub")
    if not api_key:
        raise ValueError("BREVO_API_KEY не задан")
    if not sender_email:
        raise ValueError("BREVO_SENDER_EMAIL не задан")

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px">
      <h2 style="color:#4f46e5">MediaHub</h2>
      <p>Вы запросили сброс пароля.</p>
      <p>Ваш код для сброса пароля:</p>
      <div style="font-size:36px;font-weight:800;letter-spacing:12px;color:#4f46e5;padding:20px;background:#f0f0ff;border-radius:12px;text-align:center">{code}</div>
      <p style="color:#888;font-size:13px;margin-top:20px">Код действителен 15 минут. Если вы не запрашивали сброс — проигнорируйте это письмо.</p>
    </div>
    """

    resp = http_requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email}],
            "subject": "Сброс пароля — MediaHub",
            "htmlContent": html,
        },
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Brevo error {resp.status_code}: {resp.text}")


# ── Group membership ────────────────────────────────────────────────────────

def require_group_member(group_id: int, user_id: int, conn) -> str:
    c = conn.cursor()
    c.execute("SELECT role FROM group_members WHERE group_id=%s AND user_id=%s", (group_id, user_id))
    row = c.fetchone()
    if not row:
        raise HTTPException(403, "Нет доступа к этой группе")
    return row["role"]


# ── Distance ─────────────────────────────────────────────────────────────────

def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(2 * radius * asin(sqrt(a)), 2)


# ── Upload configuration ─────────────────────────────────────────────────────

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
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


def vk_wall_post(access_token: str, group_id: str, message: str, attachments: List[str] = []) -> int:
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
    fname = os.path.basename(item["url"])
    fpath = os.path.join(UPLOAD_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, "rb") as f:
            return f.read(), item.get("filename") or fname
    file_url = f"{backend_base}{item['url']}"
    resp = http_requests.get(file_url, timeout=120)
    resp.raise_for_status()
    return resp.content, item.get("filename") or fname


def tg_send_post(bot_token: str, chat_id: str, message: str, media: List[dict], backend_base: str) -> List[int]:
    photos_videos = [m for m in media if m.get("type") in ("image", "video")]
    docs = [m for m in media if m.get("type") == "doc"]
    posted_ids: List[int] = []

    caption_with_media = len(message) <= TG_CAPTION_LIMIT and (photos_videos or docs)
    sent_text_separately = False

    if message and not caption_with_media:
        for chunk_start in range(0, len(message), TG_MESSAGE_LIMIT):
            chunk = message[chunk_start:chunk_start + TG_MESSAGE_LIMIT]
            res = tg_api(bot_token, "sendMessage", data={"chat_id": chat_id, "text": chunk})
            posted_ids.append(res.get("message_id"))
        sent_text_separately = True

    if photos_videos:
        if len(photos_videos) == 1:
            item = photos_videos[0]
            file_bytes, fname = _resolve_media_bytes(item, backend_base)
            method = "sendPhoto" if item["type"] == "image" else "sendVideo"
            field = "photo" if item["type"] == "image" else "video"
            data = {"chat_id": chat_id}
            if not sent_text_separately and message:
                data["caption"] = message[:TG_CAPTION_LIMIT]
            res = tg_api(bot_token, method, data=data, files={field: (fname, file_bytes)}, _timeout=300)
            posted_ids.append(res.get("message_id"))
        else:
            files = {}
            media_payload = []
            for idx, item in enumerate(photos_videos[:10]):
                file_bytes, fname = _resolve_media_bytes(item, backend_base)
                attach_key = f"file{idx}"
                files[attach_key] = (fname, file_bytes)
                m = {"type": "photo" if item["type"] == "image" else "video", "media": f"attach://{attach_key}"}
                if idx == 0 and not sent_text_separately and message:
                    m["caption"] = message[:TG_CAPTION_LIMIT]
                media_payload.append(m)
            res = tg_api(
                bot_token, "sendMediaGroup",
                data={"chat_id": chat_id, "media": json.dumps(media_payload)},
                files=files, _timeout=600,
            )
            if isinstance(res, list):
                posted_ids.extend(m.get("message_id") for m in res)

    for idx, item in enumerate(docs):
        file_bytes, fname = _resolve_media_bytes(item, backend_base)
        data = {"chat_id": chat_id}
        if idx == 0 and not sent_text_separately and not photos_videos and message:
            data["caption"] = message[:TG_CAPTION_LIMIT]
        res = tg_api(bot_token, "sendDocument", data=data, files={"document": (fname, file_bytes)}, _timeout=300)
        posted_ids.append(res.get("message_id"))

    if not posted_ids and message:
        res = tg_api(bot_token, "sendMessage", data={"chat_id": chat_id, "text": message[:TG_MESSAGE_LIMIT]})
        posted_ids.append(res.get("message_id"))

    return posted_ids


# ── Youth centers mock data ──────────────────────────────────────────────────

YOUTH_CENTERS_MOCK = [
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
