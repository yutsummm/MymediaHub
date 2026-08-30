import os

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg2.extras import Json

import audit
import publishing
import review
import richtext
import slots as publishing_slots
import templates
from models import (
    AIEnhanceRequest,
    GenerateRequest,
    PostCreate,
    PostPreview,
    PostQueue,
    PostUpdate,
    ReviewReject,
    TemplateSave,
)
from publish_queue import enqueue, get_job, job_for_post
from stats import save_platform_stats, serialize_post, serialize_posts
from utils import (
    _AI_PROMPTS,
    app_now,
    check_rate_limit,
    decrypt_row_secret,
    fmt_dt,
    get_current_user_id,
    get_db,
    like_pattern,
    media_for_storage,
    page_meta,
    paging,
    parse_dt,
    posts_scope,
    require_admin,
    require_group_member,
    require_post_access,
)

router = APIRouter()


# Поля поста, приходящие из запроса. Именованные параметры, а не позиционные:
# в списке из тринадцати «%s» перестановка двух соседних значений выглядит
# ровно так же, как правильный код, — и именно на этом мы уже спотыкались
# (перепутанные параметры в приёме приглашения).
POST_COLUMNS = (
    "title", "content", "status", "platforms", "tags", "scheduled_at",
    "location_address", "location_lat", "location_lng", "author_id",
    "template_type", "media", "auto_delete_at", "content_overrides", "first_comment",
)


def _post_values(body, user_id: int) -> dict:
    return {
        "title": body.title,
        "content": body.content,
        "status": body.status,
        "platforms": Json(body.platforms),
        "tags": Json(body.tags),
        "scheduled_at": parse_dt(body.scheduled_at),
        "location_address": body.location_address,
        "location_lat": body.location_lat,
        "location_lng": body.location_lng,
        "author_id": user_id,
        "template_type": body.template_type,
        "media": media_for_storage(body.media),
        "auto_delete_at": parse_dt(body.auto_delete_at),
        "content_overrides": Json(body.content_overrides or {}),
        "first_comment": body.first_comment,
    }


def _insert_post(c, body, user_id: int, gid: int | None = None) -> int:
    """Заводит пост. gid=None — пост вне группы (легаси-область без группы)."""
    values = _post_values(body, user_id)
    columns = list(POST_COLUMNS)
    if gid is not None:
        columns.append("group_id")
        values["group_id"] = gid
    c.execute(
        f"INSERT INTO posts ({', '.join(columns)}) "  # noqa: S608 — имена свои, из POST_COLUMNS
        f"VALUES ({', '.join('%(' + col + ')s' for col in columns)}) RETURNING id",
        values,
    )
    return c.fetchone()["id"]



def _record_post_deletion(conn, c, post_id: int, user_id: int, request) -> None:
    """
    След от удаления поста. Опубликованный пост особенно: в паблике он
    остаётся, а у нас исчезает — и объяснить расхождение потом нечем.
    """
    c.execute("SELECT title, status, group_id FROM posts WHERE id=%s", (post_id,))
    post = c.fetchone()
    if not post:
        return
    audit.record(
        conn, user_id, audit.POST_DELETED,
        object_type="post", object_id=post_id, object_label=post["title"],
        group_id=post["group_id"], details={"статус": post["status"]}, request=request,
    )



# ── Global Posts ──────────────────────────────────────────────────────────────

@router.get("/api/posts")
def get_posts(
    q: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
    date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    c = conn.cursor()
    scope_sql, scope_params = posts_scope(user_id, conn)
    query = (
        "SELECT p.*, u.name as author_name FROM posts p "
        f"LEFT JOIN users u ON p.author_id=u.id WHERE {scope_sql}"
    )
    params: list = list(scope_params)
    if q:
        # ILIKE, а не LOWER(...) LIKE LOWER(...): триграммный GIN-индекс
        # (миграция a9d4f1c60b72) построен по самой колонке и обслуживает
        # ILIKE, а вот LOWER(колонка) для него — уже другое выражение, и
        # запрос сваливался бы в перебор всей таблицы.
        query += " AND (p.title ILIKE %s OR p.content ILIKE %s)"
        pattern = like_pattern(q)
        params += [pattern, pattern]
    if status:
        query += " AND p.status=%s"
        params.append(status)
    if platform:
        # jsonb-оператор вместо LIKE '%"vk"%': идёт по GIN-индексу и не может
        # совпасть с подстрокой внутри чужого значения.
        query += " AND p.platforms ? %s"
        params.append(platform)
    if tag:
        query += " AND p.tags ? %s"
        params.append(tag)
    if date:
        # Раньше по дате фильтровал фронт, у себя, по уже загруженной странице.
        # С постраничной выдачей так нельзя: фильтр применялся бы к сотне
        # записей вместо всех, и «ничего не найдено» означало бы «нет на этой
        # странице». Условие то же, что рисовал фронт: первая заполненная из трёх дат.
        # Настоящее сравнение дат вместо LIKE по строке: колонки теперь
        # timestamptz, и «за такой-то день» — это интервал, а не префикс.
        query += (" AND COALESCE(p.scheduled_at, p.published_at, p.created_at)::date"
                  " = %s::date")
        params.append(date)

    # Считаем по тем же фильтрам, что и выбираем, — иначе «показаны 1–20 из 250»
    # врёт при любом фильтре.
    count_query = query.replace("SELECT p.*, u.name as author_name", "SELECT COUNT(*)", 1)
    count_params = list(params)

    limit, offset = paging(limit, offset)
    query += " ORDER BY p.created_at DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    c.execute(query, params)
    rows = c.fetchall()
    c.execute(count_query, count_params)
    total = c.fetchone()["count"]
    result = serialize_posts(conn, rows)
    conn.close()
    return {"posts": result, **page_meta(total, limit, offset)}


@router.post("/api/posts")
def create_post(body: PostCreate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    pid = _insert_post(c, body, user_id)
    conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    row = c.fetchone()
    result = serialize_post(conn, row)
    conn.close()
    return result


@router.get("/api/posts/{post_id}")
def get_post(post_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_post_access(post_id, user_id, conn)
    c.execute(
        "SELECT p.*, u.name as author_name FROM posts p LEFT JOIN users u ON p.author_id=u.id WHERE p.id=%s",
        (post_id,),
    )
    row = c.fetchone()
    result = serialize_post(conn, row)
    conn.close()
    if not row:
        raise HTTPException(404, "Пост не найден")
    return result


@router.put("/api/posts/{post_id}")
def update_post(post_id: int, body: PostUpdate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_post_access(post_id, user_id, conn, write=True)
    updates: list[str] = []
    params: list = []
    if body.title is not None:
        updates.append("title=%s")
        params.append(body.title)
    if body.content is not None:
        updates.append("content=%s")
        params.append(body.content)
    if body.status is not None:
        updates.append("status=%s")
        params.append(body.status)
    if body.platforms is not None:
        updates.append("platforms=%s")
        params.append(Json(body.platforms))
    if body.tags is not None:
        updates.append("tags=%s")
        params.append(Json(body.tags))
    if body.scheduled_at is not None:
        updates.append("scheduled_at=%s")
        params.append(parse_dt(body.scheduled_at))
    if body.media is not None:
        updates.append("media=%s")
        params.append(media_for_storage(body.media))
    if body.location_address is not None:
        updates.append("location_address=%s")
        params.append(body.location_address)
    if body.location_lat is not None:
        updates.append("location_lat=%s")
        params.append(body.location_lat)
    if body.location_lng is not None:
        updates.append("location_lng=%s")
        params.append(body.location_lng)
    if body.auto_delete_at is not None:
        # Пустая строка — «снимать не надо»: интерфейсу нужен способ убрать
        # ранее назначенный срок, а не только назначить новый.
        updates.append("auto_delete_at=%s")
        params.append(parse_dt(body.auto_delete_at))
    if body.content_overrides is not None:
        # Пустые значения не храним: «стёр текст для Telegram» означает
        # «вернуть общий», а не «опубликовать там пустоту».
        updates.append("content_overrides=%s")
        params.append(Json({k: v for k, v in body.content_overrides.items() if v.strip()}))
    if body.first_comment is not None:
        updates.append("first_comment=%s")
        params.append(body.first_comment.strip() or None)
    if updates:
        params.append(post_id)
        c.execute(f"UPDATE posts SET {', '.join(updates)} WHERE id=%s", params)
        conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    result = serialize_post(conn, row)
    conn.close()
    return result


@router.delete("/api/posts/{post_id}")
def delete_post(
    post_id: int, user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    c = conn.cursor()
    require_post_access(post_id, user_id, conn, write=True)
    _record_post_deletion(conn, c, post_id, user_id, request)
    c.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/posts/{post_id}/publish")
def publish_post(post_id: int, user_id: int = Depends(get_current_user_id)):
    """
    Ставит пост в очередь и сразу отвечает.

    Раньше отправка шла прямо здесь: загрузка видео в ВК идёт с таймаутом 120
    секунд на файл, и тяжёлый пост либо подвешивал запрос, либо отваливался по
    таймауту прокси — а пост к тому моменту мог уже уйти.
    """
    conn = get_db()
    try:
        post = require_post_access(post_id, user_id, conn, write=True)
        return enqueue(conn, post["id"], post.get("group_id"), user_id)
    finally:
        conn.close()


# ── Group-scoped Posts ──────────────────────────────────────────────────────

@router.get("/api/groups/{gid}/posts")
def get_group_posts(
    gid: int,
    q: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
    date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    c = conn.cursor()
    require_group_member(gid, user_id, conn)
    query = "SELECT p.*, u.name as author_name FROM posts p LEFT JOIN users u ON p.author_id=u.id WHERE p.group_id=%s"
    params: list = [gid]
    if q:
        # ILIKE, а не LOWER(...) LIKE LOWER(...): триграммный GIN-индекс
        # (миграция a9d4f1c60b72) построен по самой колонке и обслуживает
        # ILIKE, а вот LOWER(колонка) для него — уже другое выражение, и
        # запрос сваливался бы в перебор всей таблицы.
        query += " AND (p.title ILIKE %s OR p.content ILIKE %s)"
        pattern = like_pattern(q)
        params += [pattern, pattern]
    if status:
        query += " AND p.status=%s"
        params.append(status)
    if platform:
        # jsonb-оператор вместо LIKE '%"vk"%': идёт по GIN-индексу и не может
        # совпасть с подстрокой внутри чужого значения.
        query += " AND p.platforms ? %s"
        params.append(platform)
    if tag:
        query += " AND p.tags ? %s"
        params.append(tag)
    if date:
        # Настоящее сравнение дат вместо LIKE по строке: колонки теперь
        # timestamptz, и «за такой-то день» — это интервал, а не префикс.
        query += (" AND COALESCE(p.scheduled_at, p.published_at, p.created_at)::date"
                  " = %s::date")
        params.append(date)

    count_query = query.replace("SELECT p.*, u.name as author_name", "SELECT COUNT(*)", 1)
    count_params = list(params)

    limit, offset = paging(limit, offset)
    query += " ORDER BY p.created_at DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    c.execute(query, params)
    rows = c.fetchall()
    c.execute(count_query, count_params)
    total = c.fetchone()["count"]
    result = serialize_posts(conn, rows)
    conn.close()
    return {"posts": result, **page_meta(total, limit, offset)}


@router.post("/api/groups/{gid}/posts")
def create_group_post(gid: int, body: PostCreate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role == "volunteer":
        conn.close()
        raise HTTPException(403, "Наблюдатели не могут создавать посты")
    try:
        review.check_may_release(conn, gid, role, body.status)
    except HTTPException:
        conn.close()
        raise
    pid = _insert_post(c, body, user_id, gid)
    conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    row = c.fetchone()
    result = serialize_post(conn, row)
    conn.close()
    return result


@router.get("/api/groups/{gid}/posts/{post_id}")
def get_group_post(gid: int, post_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_group_member(gid, user_id, conn)
    c.execute(
        "SELECT p.*, u.name as author_name FROM posts p LEFT JOIN users u ON p.author_id=u.id "
        "WHERE p.id=%s AND p.group_id=%s",
        (post_id, gid),
    )
    row = c.fetchone()
    result = serialize_post(conn, row)
    conn.close()
    if not row:
        raise HTTPException(404, "Пост не найден")
    return result


@router.put("/api/groups/{gid}/posts/{post_id}")
def update_group_post(gid: int, post_id: int, body: PostUpdate, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role == "volunteer":
        conn.close()
        raise HTTPException(403, "Наблюдатели не могут редактировать посты")
    c.execute("SELECT id FROM posts WHERE id=%s AND group_id=%s", (post_id, gid))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Пост не найден")
    try:
        review.check_may_release(conn, gid, role, body.status)
    except HTTPException:
        conn.close()
        raise
    updates: list[str] = []
    params: list = []
    if body.title is not None:
        updates.append("title=%s")
        params.append(body.title)
    if body.content is not None:
        updates.append("content=%s")
        params.append(body.content)
    if body.status is not None:
        updates.append("status=%s")
        params.append(body.status)
    if body.platforms is not None:
        updates.append("platforms=%s")
        params.append(Json(body.platforms))
    if body.tags is not None:
        updates.append("tags=%s")
        params.append(Json(body.tags))
    if body.scheduled_at is not None:
        updates.append("scheduled_at=%s")
        params.append(parse_dt(body.scheduled_at))
    if body.media is not None:
        updates.append("media=%s")
        params.append(media_for_storage(body.media))
    if body.location_address is not None:
        updates.append("location_address=%s")
        params.append(body.location_address)
    if body.location_lat is not None:
        updates.append("location_lat=%s")
        params.append(body.location_lat)
    if body.location_lng is not None:
        updates.append("location_lng=%s")
        params.append(body.location_lng)
    if body.auto_delete_at is not None:
        # Пустая строка — «снимать не надо»: интерфейсу нужен способ убрать
        # ранее назначенный срок, а не только назначить новый.
        updates.append("auto_delete_at=%s")
        params.append(parse_dt(body.auto_delete_at))
    if body.content_overrides is not None:
        # Пустые значения не храним: «стёр текст для Telegram» означает
        # «вернуть общий», а не «опубликовать там пустоту».
        updates.append("content_overrides=%s")
        params.append(Json({k: v for k, v in body.content_overrides.items() if v.strip()}))
    if body.first_comment is not None:
        updates.append("first_comment=%s")
        params.append(body.first_comment.strip() or None)
    if updates:
        params.append(post_id)
        c.execute(f"UPDATE posts SET {', '.join(updates)} WHERE id=%s", params)
        conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    result = serialize_post(conn, row)
    conn.close()
    return result


@router.delete("/api/groups/{gid}/posts/{post_id}")
def delete_group_post(
    gid: int, post_id: int,
    user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role == "volunteer":
        conn.close()
        raise HTTPException(403, "Наблюдатели не могут удалять посты")
    c.execute("SELECT id FROM posts WHERE id=%s AND group_id=%s", (post_id, gid))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404)
    _record_post_deletion(conn, c, post_id, user_id, request)
    c.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/groups/{gid}/posts/{post_id}/publish")
def publish_group_post(gid: int, post_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role == "volunteer":
        conn.close()
        raise HTTPException(403, "Наблюдатели не могут публиковать посты")
    c.execute("SELECT id FROM posts WHERE id=%s AND group_id=%s", (post_id, gid))
    post = c.fetchone()
    if not post:
        conn.close()
        raise HTTPException(404, "Пост не найден")
    try:
        # Кнопка публикации — тот же выход в свет, что и статус: закрыв только
        # статусы, мы оставили бы дверь рядом открытой.
        review.check_may_release(conn, gid, role, "published")
        return enqueue(conn, post_id, gid, user_id)
    finally:
        conn.close()


# ── Предпросмотр ─────────────────────────────────────────────────────────────

# Предел длины сообщения на площадке — тот же, что применяется при отправке.
PLATFORM_LIMITS = {"vk": 16000, "telegram": 4096}
PLATFORM_NAMES = {"vk": "ВКонтакте", "telegram": "Telegram"}


@router.post("/api/groups/{gid}/posts/preview")
def preview_post(gid: int, body: PostPreview, user_id: int = Depends(get_current_user_id)):
    """
    Как пост будет выглядеть на каждой площадке.

    Считает тот же код, что и публикация (`publishing.compose`). Собирать
    предпросмотр отдельно на клиенте значило бы завести вторую копию правил —
    подстановок, меток, разворота ссылок, — и она разошлась бы с настоящей.
    Предпросмотр, который врёт, хуже отсутствующего: на него полагаются.

    Ссылки отдаются кусками, а не готовым HTML: интерфейсу нужно их
    отрисовать, а не вставить чужую разметку внутрь страницы.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдателям предпросмотр недоступен")
        c = conn.cursor()
        settings = publishing._group_content_settings(c, gid)
        draft = {
            "title": body.title,
            "content": body.content,
            "content_overrides": body.content_overrides or {},
            "tags": body.tags,
        }

        result = []
        for platform in body.platforms:
            if platform not in PLATFORM_NAMES:
                continue
            text = publishing.compose(draft, settings, platform)
            limit = PLATFORM_LIMITS[platform]
            length = richtext.visible_length(text)
            item = {
                "platform": platform,
                "label": PLATFORM_NAMES[platform],
                "segments": [{"kind": kind, "text": chunk, "url": url}
                             for kind, chunk, url in richtext.segments(text)],
                "length": length,
                "limit": limit,
                "over_limit": length > limit,
            }
            if platform == "vk" and (body.first_comment or "").strip():
                comment = publishing.compose(
                    {"content": body.first_comment, "tags": body.tags}, settings, "vk")
                item["first_comment"] = comment
            result.append(item)
        return {"previews": result}
    finally:
        conn.close()


# ── Очередь по расписанию ────────────────────────────────────────────────────

@router.post("/api/groups/{gid}/posts/{post_id}/queue")
def queue_group_post(
    gid: int, post_id: int, body: PostQueue,
    user_id: int = Depends(get_current_user_id),
):
    """
    Ставит пост в ближайшее свободное окно расписания.

    Отдельная ручка, а не «передайте scheduled_at»: смысл очереди в том, что
    время считает сервер по расписанию группы, и считать его на клиенте
    значило бы держать копию правил в двух местах.

    Пост получает обычный `scheduled_at` и обычный статус `scheduled` —
    очередь не становится вторым механизмом публикации рядом с планировщиком.
    Там, где нужна виза, статус остаётся прежним: окно занято, но выпустит
    пост администратор.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдатели не могут планировать посты")
        c = conn.cursor()
        c.execute("SELECT id, status FROM posts WHERE id=%s AND group_id=%s", (post_id, gid))
        post = c.fetchone()
        if not post:
            raise HTTPException(404, "Пост не найден")
        if post["status"] == "published":
            raise HTTPException(409, "Опубликованный пост в очередь не ставится")

        at = publishing_slots.next_free_slot(conn, gid, exclude_post_id=post_id)
        may_release = review.may_release(conn, gid, role)
        status = "scheduled" if may_release else post["status"]
        c.execute(
            "UPDATE posts SET scheduled_at=%s, status=%s, auto_delete_at=%s WHERE id=%s",
            (at, status, parse_dt(body.auto_delete_at), post_id),
        )
        conn.commit()
        c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
        result = serialize_post(conn, c.fetchone())
        # Отдельно говорим, дошло ли дело до расписания: при обязательном
        # согласовании окно занято, но выйдет пост только после визы, и
        # интерфейс обязан сказать об этом прямо.
        result["queued"] = may_release
        return result
    finally:
        conn.close()


# ── История поста ────────────────────────────────────────────────────────────

def _post_history(conn, post: dict) -> list[dict]:
    """
    Что с постом происходило: создание, согласование, публикация, снятие.

    Часть событий выводится из самого поста (создан, опубликован, снят), часть
    берётся из журнала действий. Заводить записи журнала на создание поста
    ради ленты не стали: `posts.created_at` и так знает, когда это было, а
    журнал существует для необратимого — засорять его обычной работой значит
    сделать бесполезным поиск по нему.
    """
    events: list[dict] = []
    if post.get("created_at"):
        events.append({"at": fmt_dt(post["created_at"]), "action": "created",
                       "label": "Создан", "actor": post.get("author_name"), "details": None})

    c = conn.cursor()
    # Имя, а не почта: в ленте событий «irina-640e38@demo.local» читается как
    # техническая строка. Почта остаётся запасным вариантом — автора могли
    # удалить, и тогда в журнале от него останется только она.
    c.execute(
        "SELECT a.created_at, a.action, a.details, "
        "       COALESCE(u.name, a.actor_email) AS actor "
        "FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
        "WHERE a.object_type='post' AND a.object_id=%s ORDER BY a.id",
        (post["id"],),
    )
    LABELS = {
        "post.submitted": "Отправлен на согласование",
        "post.approved": "Согласован",
        "post.rejected": "Возвращён на доработку",
        "post.deleted": "Удалён",
    }
    for row in c.fetchall():
        details = row["details"] or {}
        events.append({
            "at": fmt_dt(row["created_at"]),
            "action": row["action"],
            "label": LABELS.get(row["action"], row["action"]),
            "actor": row["actor"],
            "details": details.get("замечание") or details.get("выпуск"),
        })

    if post.get("published_at"):
        events.append({"at": fmt_dt(post["published_at"]), "action": "published",
                       "label": "Опубликован", "actor": None,
                       "details": post.get("publish_error")})
    if post.get("removed_at"):
        events.append({"at": fmt_dt(post["removed_at"]), "action": "removed",
                       "label": "Снят с публикации", "actor": None, "details": None})

    events.sort(key=lambda e: e["at"] or "")
    return events


@router.get("/api/posts/{post_id}/history")
def get_post_history(post_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        require_post_access(post_id, user_id, conn)
        c = conn.cursor()
        c.execute(
            "SELECT p.*, u.name as author_name FROM posts p "
            "LEFT JOIN users u ON u.id = p.author_id WHERE p.id=%s",
            (post_id,),
        )
        return {"events": _post_history(conn, dict(c.fetchone()))}
    finally:
        conn.close()


# ── Согласование ─────────────────────────────────────────────────────────────
# Отдельная тройка ручек вместо «поставьте статус on_review через PUT»: у
# перехода есть побочные действия — уведомить администраторов, записать в
# журнал, при одобрении выпустить пост, — и прятать их внутрь обновления поля
# значило бы, что любой PUT со статусом молча рассылает уведомления.

def _review_post(gid: int, post_id: int, user_id: int, conn, admin_only: bool):
    role = require_group_member(gid, user_id, conn)
    if admin_only and role != "admin":
        raise HTTPException(403, "Согласовывать посты может только администратор группы")
    if role == "volunteer":
        raise HTTPException(403, "Наблюдатели не работают с постами")
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id=%s AND group_id=%s", (post_id, gid))
    post = c.fetchone()
    if not post:
        raise HTTPException(404, "Пост не найден")
    return post


@router.post("/api/groups/{gid}/posts/{post_id}/submit")
def submit_group_post(
    gid: int, post_id: int,
    user_id: int = Depends(get_current_user_id), request: Request = None,
):
    """Отправляет пост на согласование администратору группы."""
    conn = get_db()
    try:
        post = _review_post(gid, post_id, user_id, conn, admin_only=False)
        review.submit(conn, post, user_id, request)
        return {"status": "on_review"}
    finally:
        conn.close()


@router.post("/api/groups/{gid}/posts/{post_id}/approve")
def approve_group_post(
    gid: int, post_id: int,
    user_id: int = Depends(get_current_user_id), request: Request = None,
):
    """Одобряет пост: он уходит в расписание или сразу в очередь публикации."""
    conn = get_db()
    try:
        post = _review_post(gid, post_id, user_id, conn, admin_only=True)
        return review.approve(conn, post, user_id, request)
    finally:
        conn.close()


@router.post("/api/groups/{gid}/posts/{post_id}/reject")
def reject_group_post(
    gid: int, post_id: int, body: ReviewReject,
    user_id: int = Depends(get_current_user_id), request: Request = None,
):
    """Возвращает пост автору с замечанием."""
    conn = get_db()
    try:
        post = _review_post(gid, post_id, user_id, conn, admin_only=True)
        review.reject(conn, post, user_id, body.comment, request)
        return {"status": "draft"}
    finally:
        conn.close()


@router.get("/api/publish-jobs/{job_id}")
def get_publish_job(job_id: int, user_id: int = Depends(get_current_user_id)):
    """Состояние задачи публикации — по нему интерфейс ждёт результата."""
    conn = get_db()
    try:
        job = get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "Задача не найдена")
        # Право смотреть задачу — это право на сам пост
        require_post_access(job["post_id"], user_id, conn)
        return job
    finally:
        conn.close()


@router.get("/api/posts/{post_id}/publish-job")
def get_post_publish_job(post_id: int, user_id: int = Depends(get_current_user_id)):
    """Последняя задача по посту: интерфейс восстанавливает состояние после перезагрузки."""
    conn = get_db()
    try:
        require_post_access(post_id, user_id, conn)
        return job_for_post(conn, post_id) or {"state": "none", "post_id": post_id}
    finally:
        conn.close()


# ── VK Stats Sync ────────────────────────────────────────────────────────────

@router.post("/api/posts/sync-vk-stats")
def sync_vk_stats(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_admin(user_id, conn)
    c.execute("SELECT group_id, access_token FROM vk_settings WHERE id=1")
    vk = decrypt_row_secret(c.fetchone(), "access_token")
    if not vk:
        conn.close()
        return {"synced": 0, "message": "VK не подключён"}
    c.execute("SELECT DISTINCT vk.group_id, vk.access_token FROM vk_settings vk WHERE vk.workspace_id IS NOT NULL")
    all_vk = [row for row in (decrypt_row_secret(r, "access_token") for r in c.fetchall()) if row]
    if vk:
        all_vk.append(dict(vk))
    seen = set()
    unique_vk = []
    for v in all_vk:
        if v["group_id"] not in seen:
            seen.add(v["group_id"])
            unique_vk.append(v)

    total_synced = 0
    for vk_conf in unique_vk:
        gid = vk_conf["group_id"]
        token = vk_conf["access_token"]
        c.execute(
            "SELECT id, vk_post_id FROM posts WHERE vk_post_id IS NOT NULL AND vk_post_id != '' AND status='published'"
        )
        posts = c.fetchall()
        if not posts:
            continue
        batch = []
        for p in posts:
            batch.append(f"-{gid}_{p['vk_post_id']}")
        for i in range(0, len(batch), 100):
            chunk = batch[i:i + 100]
            try:
                r = http_requests.get(
                    "https://api.vk.com/method/wall.getById",
                    params={"posts": ",".join(chunk), "access_token": token, "v": "5.199"},
                    timeout=15,
                )
                data = r.json()
                if "error" in data:
                    continue
                vk_posts = data.get("response", [])
                if not vk_posts:
                    continue
                for vp in vk_posts:
                    vp_id = str(vp.get("id"))
                    views = vp.get("views", {}).get("count", 0) if vp.get("views") else 0
                    reactions = vp.get("likes", {}).get("count", 0) if vp.get("likes") else 0
                    comments = vp.get("comments", {}).get("count", 0) if vp.get("comments") else 0
                    shares = vp.get("reposts", {}).get("count", 0) if vp.get("reposts") else 0
                    # Пишем в строку площадки «vk»: общие колонки затирали бы
                    # цифры Telegram, как только тот начнёт отдавать данные.
                    c.execute(
                        "SELECT id FROM posts WHERE vk_post_id=%s AND status='published'",
                        (vp_id,),
                    )
                    for row in c.fetchall():
                        save_platform_stats(
                            conn, row["id"], "vk", views=views, reactions=reactions,
                            comments=comments, shares=shares,
                        )
                        c.execute(
                            "UPDATE posts SET vk_stats_updated_at=%s WHERE id=%s",
                            (app_now(), row["id"]),
                        )
                        total_synced += 1
            except Exception:
                continue
    conn.commit()
    conn.close()
    return {"synced": total_synced, "message": f"Обновлено {total_synced} постов"}


@router.post("/api/groups/{gid}/posts/sync-vk-stats")
def group_sync_vk_stats(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_group_member(gid, user_id, conn)

    c.execute("SELECT group_id, access_token FROM vk_settings WHERE group_id=%s", (str(gid),))
    vk = decrypt_row_secret(c.fetchone(), "access_token")
    if not vk:
        conn.close()
        return {"synced": 0, "message": "VK не подключён для этой группы"}

    gid_vk = vk["group_id"]
    token = vk["access_token"]

    c.execute(
        "SELECT id, vk_post_id FROM posts WHERE group_id=%s AND vk_post_id IS NOT NULL AND vk_post_id != '' AND status='published'",
        (gid,),
    )
    posts = c.fetchall()
    if not posts:
        conn.close()
        return {"synced": 0, "message": "Нет опубликованных постов с VK ID"}

    total_synced = 0
    batch = []
    for p in posts:
        batch.append(f"-{gid_vk}_{p['vk_post_id']}")
    for i in range(0, len(batch), 100):
        chunk = batch[i:i + 100]
        try:
            r = http_requests.get(
                "https://api.vk.com/method/wall.getById",
                params={"posts": ",".join(chunk), "access_token": token, "v": "5.199"},
                timeout=15,
            )
            data = r.json()
            if "error" in data:
                continue
            vk_posts = data.get("response", [])
            if not vk_posts:
                continue
            for vp in vk_posts:
                vp_id = str(vp.get("id"))
                views = vp.get("views", {}).get("count", 0) if vp.get("views") else 0
                reactions = vp.get("likes", {}).get("count", 0) if vp.get("likes") else 0
                comments = vp.get("comments", {}).get("count", 0) if vp.get("comments") else 0
                shares = vp.get("reposts", {}).get("count", 0) if vp.get("reposts") else 0
                c.execute(
                    "SELECT id FROM posts WHERE vk_post_id=%s AND group_id=%s AND status='published'",
                    (vp_id, gid),
                )
                for row in c.fetchall():
                    save_platform_stats(
                        conn, row["id"], "vk", views=views, reactions=reactions,
                        comments=comments, shares=shares,
                    )
                    c.execute(
                        "UPDATE posts SET vk_stats_updated_at=%s WHERE id=%s",
                        (app_now(), row["id"]),
                    )
                    total_synced += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return {"synced": total_synced, "message": f"Обновлено {total_synced} постов"}


# ── Calendar ─────────────────────────────────────────────────────────────────

@router.get("/api/calendar")
def get_calendar(
    start: str = Query(...),
    end: str = Query(...),
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    c = conn.cursor()
    scope_sql, scope_params = posts_scope(user_id, conn, alias="")
    c.execute(
        "SELECT id,title,status,platforms,tags,scheduled_at,published_at,created_at FROM posts "
        f"WHERE {scope_sql} AND ("
        "(scheduled_at::date BETWEEN %s::date AND %s::date) "
        " OR (published_at::date BETWEEN %s::date AND %s::date) "
        " OR (created_at::date BETWEEN %s::date AND %s::date)) "
        "ORDER BY COALESCE(scheduled_at, published_at, created_at)",
        scope_params + [start, end, start, end, start, end],
    )
    rows = c.fetchall()
    result = serialize_posts(conn, rows)
    conn.close()
    return result


# ── Templates ─────────────────────────────────────────────────────────────────

@router.get("/api/templates")
def get_templates(user_id: int = Depends(get_current_user_id)):
    """Встроенные шаблоны плюс шаблоны групп, где человек состоит."""
    conn = get_db()
    try:
        return templates.visible_to(conn, user_id)
    finally:
        conn.close()


@router.post("/api/groups/{gid}/templates")
def create_template(gid: int, body: TemplateSave, user_id: int = Depends(get_current_user_id)):
    """
    Заводит шаблон группы.

    Владелец — группа, а не человек: шаблон описывает, как публикует
    учреждение, и должен остаться, когда автор уйдёт.
    """
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдатели не могут заводить шаблоны")
        name = (body.name or "").strip()
        text = (body.template_text or "").strip()
        if not name:
            raise HTTPException(400, "У шаблона должно быть название")
        if not text:
            raise HTTPException(400, "Шаблон без текста бесполезен")

        fields = templates.extract_fields(text, body.title_template or "")
        c = conn.cursor()
        c.execute(
            "INSERT INTO templates (name, type, description, fields, template_text, "
            "  title_template, group_id, created_by) "
            "VALUES (%(name)s, %(type)s, %(description)s, %(fields)s, %(text)s, "
            "        %(title)s, %(gid)s, %(user_id)s) "
            # Повторное название внутри группы — это правка того же шаблона,
            # а не второй такой же: человек ожидает, что «сохранить» перезапишет.
            "ON CONFLICT (group_id, type) WHERE group_id IS NOT NULL DO UPDATE SET "
            "  name=EXCLUDED.name, description=EXCLUDED.description, "
            "  fields=EXCLUDED.fields, template_text=EXCLUDED.template_text, "
            "  title_template=EXCLUDED.title_template "
            "RETURNING *",
            {"name": name, "type": templates.slug(name, gid),
             "description": (body.description or "").strip(),
             "fields": Json(fields), "text": text,
             "title": (body.title_template or "").strip() or None,
             "gid": gid, "user_id": user_id},
        )
        result = templates.serialize(c.fetchone())
        conn.commit()
        return result
    finally:
        conn.close()


@router.delete("/api/groups/{gid}/templates/{template_id}")
def delete_template(gid: int, template_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        role = require_group_member(gid, user_id, conn)
        if role == "volunteer":
            raise HTTPException(403, "Наблюдатели не могут удалять шаблоны")
        c = conn.cursor()
        # group_id в условии обязателен: без него удаление добралось бы до
        # встроенных шаблонов, общих для всех групп.
        c.execute("DELETE FROM templates WHERE id=%s AND group_id=%s RETURNING id",
                  (template_id, gid))
        if not c.fetchone():
            raise HTTPException(404, "Шаблон не найден")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# Заголовки встроенных шаблонов. У своих заголовок берётся из
# title_template — правила «на каждый тип своя формула» для произвольного
# шаблона не существует.
BUILTIN_TITLES = {
    "announcement": lambda f: "Анонс: " + f.get("event_name", ""),
    "results": lambda f: "Итоги: " + f.get("event_name", ""),
    "vacancy": lambda f: "Вакансия: " + f.get("position", ""),
    "grant": lambda f: f.get("grant_name", ""),
}


@router.post("/api/generate-text")
def generate_text(body: GenerateRequest, user_id: int = Depends(get_current_user_id)):
    """Собирает текст поста из шаблона и заполненных полей."""
    conn = get_db()
    try:
        tmpl = templates.find(conn, body.template_type, user_id)
    finally:
        conn.close()

    text = templates.render(tmpl["template_text"], body.fields)
    if tmpl.get("title_template"):
        title = templates.render(tmpl["title_template"], body.fields).strip()
    elif body.template_type in BUILTIN_TITLES:
        title = BUILTIN_TITLES[body.template_type](body.fields)
    else:
        # Своего заголовка нет — берём название шаблона: оно всяко ближе к делу,
        # чем «Новый пост», и человек его тут же поправит.
        title = tmpl["name"]
    return {"text": text, "title": title or "Новый пост"}


# ── AI Enhance ───────────────────────────────────────────────────────────────

# Модель Groq — в переменной окружения, а не в коде. Поставщик выводит модели
# из обращения без предупреждения: llama-3.1-8b-instant, на которой ИИ-помощник
# работал, однажды просто исчезла, и починка потребовала выкатки. Замена модели
# не должна стоить релиза.
# Выбрано сравнением на наших же промптах с русским текстом, а не по названию.
# openai/gpt-oss-20b дважды упёрся в лимит запросов посреди прогона и выдавал
# мусор («#примир» из «пр. Мира»); openai/gpt-oss-120b отвечает Markdown —
# «**жирный**» и списки, — а текст уходит в соцсети обычным текстом, и
# звёздочки опубликовались бы буквально.
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"


def groq_model() -> str:
    return os.getenv("GROQ_MODEL", "").strip() or DEFAULT_GROQ_MODEL


def _ai_failure(error, model: str) -> HTTPException:
    """
    Превращает отказ Groq в сообщение, по которому видно, что чинить.

    Раньше любая ошибка приходила как «Ошибка Groq API: …», и человек шёл
    проверять ключи — даже когда ключ был в полном порядке, а исчезла модель.
    Разница между «ключ не приняли» и «модели больше нет» — это разные
    действия, и сообщение обязано их различать.
    """
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    detail = ""
    if response is not None:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            # Не всякий отказ приходит с разбираемым телом; тогда обойдёмся кодом.
            pass

    if status in (401, 403):
        return HTTPException(503, (
            "Groq не принял ключ доступа. Проверьте GROQ_API_KEY: ключ мог быть "
            "отозван или заменён. Новый берётся на console.groq.com/keys. "
            f"Ответ сервиса: {detail or status}"
        ))
    if status == 404:
        return HTTPException(503, (
            f"Модель «{model}» у Groq недоступна — её вывели из обращения или "
            "она не открыта для вашего ключа. Ключ при этом может быть исправен. "
            "Укажите другую в переменной GROQ_MODEL; список доступных — "
            "console.groq.com/docs/models."
        ))
    if status == 429:
        return HTTPException(429, (
            "Groq временно отказывает: исчерпан лимит запросов. "
            "Подождите минуту и попробуйте снова."
        ))
    return HTTPException(502, f"Ошибка Groq API: {detail or str(error)}")



@router.post("/api/ai-enhance")
def ai_enhance(body: AIEnhanceRequest, user_id: int = Depends(get_current_user_id)):
    # Ключ по пользователю, а не по IP: за прокси Railway у всех клиентов один IP,
    # и лимит по IP превратился бы в общий лимит на весь сервис.
    check_rate_limit(f"ai:{user_id}", 15, 60)
    if not body.text.strip():
        raise HTTPException(400, "Текст не может быть пустым")

    system_prompt = _AI_PROMPTS.get(body.mode)
    if not system_prompt:
        raise HTTPException(400, "Неверный режим. Допустимые значения: creative, russify, shortify, formal, hashtags, calltoaction")

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise HTTPException(503, (
            "GROQ_API_KEY не настроен. "
            "Получите бесплатный ключ на console.groq.com и добавьте его в .env"
        ))
    model = groq_model()

    try:
        resp = http_requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body.text},
                ],
                "temperature": {"creative": 0.75, "shortify": 0.3, "formal": 0.3,
                                "hashtags": 0.5, "calltoaction": 0.6, "russify": 0.25}.get(body.mode, 0.5),
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
        raise _ai_failure(e, model)
    except http_requests.exceptions.RequestException as e:
        raise HTTPException(502, f"Ошибка связи с ИИ: {str(e)}")
    except (KeyError, IndexError):
        raise HTTPException(502, "Неожиданный формат ответа от ИИ")
