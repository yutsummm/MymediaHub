import json
import os

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Query

from models import AIEnhanceRequest, GenerateRequest, PostCreate, PostUpdate
from publish_queue import enqueue, get_job, job_for_post
from stats import save_platform_stats, serialize_post, serialize_posts
from utils import (
    _AI_PROMPTS,
    app_now_str,
    check_rate_limit,
    decrypt_row_secret,
    get_current_user_id,
    get_db,
    media_for_storage,
    page_meta,
    paging,
    posts_scope,
    require_admin,
    require_group_member,
    require_post_access,
)

router = APIRouter()


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
        query += " AND (LOWER(p.title) LIKE LOWER(%s) OR LOWER(p.content) LIKE LOWER(%s))"
        params += [f'%{q}%', f'%{q}%']
    if status:
        query += " AND p.status=%s"
        params.append(status)
    if platform:
        query += " AND p.platforms LIKE %s"
        params.append(f'%"{platform}"%')
    if tag:
        query += " AND p.tags LIKE %s"
        params.append(f'%"{tag}"%')
    if date:
        # Раньше по дате фильтровал фронт, у себя, по уже загруженной странице.
        # С постраничной выдачей так нельзя: фильтр применялся бы к сотне
        # записей вместо всех, и «ничего не найдено» означало бы «нет на этой
        # странице». Условие то же, что рисовал фронт: первая заполненная из трёх дат.
        query += " AND COALESCE(NULLIF(p.scheduled_at,''), NULLIF(p.published_at,''), p.created_at) LIKE %s"
        params.append(f"{date}%")

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
    c.execute(
        "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,"
        "location_address,location_lat,location_lng,author_id,template_type,media) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (body.title, body.content, body.status, json.dumps(body.platforms),
         json.dumps(body.tags), body.scheduled_at, body.location_address,
         body.location_lat, body.location_lng, user_id, body.template_type,
         media_for_storage(body.media)),
    )
    pid = c.fetchone()["id"]
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
    updates, params = [], []
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
        params.append(json.dumps(body.platforms))
    if body.tags is not None:
        updates.append("tags=%s")
        params.append(json.dumps(body.tags))
    if body.scheduled_at is not None:
        updates.append("scheduled_at=%s")
        params.append(body.scheduled_at)
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
def delete_post(post_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_post_access(post_id, user_id, conn, write=True)
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
        query += " AND (LOWER(p.title) LIKE LOWER(%s) OR LOWER(p.content) LIKE LOWER(%s))"
        params += [f'%{q}%', f'%{q}%']
    if status:
        query += " AND p.status=%s"
        params.append(status)
    if platform:
        query += " AND p.platforms LIKE %s"
        params.append(f'%"{platform}"%')
    if tag:
        query += " AND p.tags LIKE %s"
        params.append(f'%"{tag}"%')
    if date:
        query += " AND COALESCE(NULLIF(p.scheduled_at,''), NULLIF(p.published_at,''), p.created_at) LIKE %s"
        params.append(f"{date}%")

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
    c.execute(
        "INSERT INTO posts (title,content,status,platforms,tags,scheduled_at,"
        "location_address,location_lat,location_lng,author_id,template_type,media,group_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (body.title, body.content, body.status, json.dumps(body.platforms),
         json.dumps(body.tags), body.scheduled_at, body.location_address,
         body.location_lat, body.location_lng, user_id, body.template_type,
         media_for_storage(body.media), gid),
    )
    pid = c.fetchone()["id"]
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
    updates, params = [], []
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
        params.append(json.dumps(body.platforms))
    if body.tags is not None:
        updates.append("tags=%s")
        params.append(json.dumps(body.tags))
    if body.scheduled_at is not None:
        updates.append("scheduled_at=%s")
        params.append(body.scheduled_at)
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
def delete_group_post(gid: int, post_id: int, user_id: int = Depends(get_current_user_id)):
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
        return enqueue(conn, post_id, gid, user_id)
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
    all_vk = [decrypt_row_secret(r, "access_token") for r in c.fetchall()]
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
                            (app_now_str(), row["id"]),
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
                        (app_now_str(), row["id"]),
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
        "(scheduled_at BETWEEN %s AND %s) OR (published_at BETWEEN %s AND %s) OR (created_at BETWEEN %s AND %s)) "
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


@router.post("/api/generate-text")
def generate_text(body: GenerateRequest, user_id: int = Depends(get_current_user_id)):
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
        "results": "Итоги: " + body.fields.get("event_name", ""),
        "vacancy": "Вакансия: " + body.fields.get("position", ""),
        "grant": body.fields.get("grant_name", ""),
    }
    return {"text": text, "title": titles.get(body.template_type, "Новый пост")}


# ── AI Enhance ───────────────────────────────────────────────────────────────

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
