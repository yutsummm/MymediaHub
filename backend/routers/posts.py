import datetime
import json
import os

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Query

from models import AIEnhanceRequest, GenerateRequest, PostCreate, PostUpdate
from utils import (
    _AI_PROMPTS,
    UPLOAD_DIR,
    check_rate_limit,
    decrypt_row_secret,
    get_current_user_id,
    get_db,
    posts_scope,
    require_admin,
    require_group_member,
    require_post_access,
    row_to_dict,
    tg_send_post,
    vk_upload_doc_to_wall,
    vk_upload_photo_to_wall,
    vk_upload_video_to_wall,
    vk_wall_post,
)

router = APIRouter()


# ── Global Posts ──────────────────────────────────────────────────────────────

@router.get("/api/posts")
def get_posts(
    q: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
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
    query += " ORDER BY p.created_at DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    c.execute(query, params)
    rows = c.fetchall()
    c.execute(f"SELECT COUNT(*) FROM posts p WHERE {scope_sql}", scope_params)
    total = c.fetchone()["count"]
    conn.close()
    return {"posts": [row_to_dict(r) for r in rows], "total": total}


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
         json.dumps([m.dict() for m in body.media])),
    )
    pid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    row = c.fetchone()
    conn.close()
    return row_to_dict(row)


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
    conn.close()
    if not row:
        raise HTTPException(404, "Пост не найден")
    return row_to_dict(row)


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
        params.append(json.dumps([m.dict() for m in body.media]))
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
    conn.close()
    return row_to_dict(row)


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
    conn = get_db()
    c = conn.cursor()
    post = require_post_access(post_id, user_id, conn, write=True)
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute(
        "UPDATE posts SET status='published',published_at=%s,views=0,reactions=0,comments=0,shares=0 WHERE id=%s",
        (now, post_id),
    )
    conn.commit()

    post_dict = row_to_dict(post)
    vk_post_id = None
    vk_error = None
    photo_errors: list = []

    platforms = post_dict.get("platforms", [])
    if "vk" in platforms:
        c.execute("SELECT group_id, access_token FROM vk_settings WHERE id=1")
        vk = decrypt_row_secret(c.fetchone(), "access_token")
        if vk:
            try:
                message = f"{post_dict['title']}\n\n{post_dict['content']}"
                attachments = []
                backend_base = os.getenv("BACKEND_URL", "https://backend-production-30d6.up.railway.app").rstrip("/")
                for item in (post_dict.get("media") or []):
                    item_type = item.get("type")
                    if item_type not in ("image", "video", "doc"):
                        continue
                    fname = os.path.basename(item["url"])
                    orig_name = item.get("filename") or fname
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    try:
                        if os.path.exists(fpath):
                            with open(fpath, "rb") as f:
                                file_data = f.read()
                        else:
                            file_url = f"{backend_base}{item['url']}"
                            resp = http_requests.get(file_url, timeout=120)
                            resp.raise_for_status()
                            file_data = resp.content
                        if item_type == "image":
                            att = vk_upload_photo_to_wall(vk["access_token"], vk["group_id"], file_data, fname)
                        elif item_type == "video":
                            att = vk_upload_video_to_wall(
                                vk["access_token"], vk["group_id"], file_data, fname,
                                title=post_dict.get("title", ""),
                                description=post_dict.get("content", ""),
                            )
                        else:
                            att = vk_upload_doc_to_wall(
                                vk["access_token"], vk["group_id"], file_data, orig_name,
                                title=post_dict.get("title", "") or orig_name,
                            )
                        attachments.append(att)
                    except Exception as media_err:
                        msg = str(media_err)
                        if any(kw in msg.lower() for kw in [
                            "unavailable with group auth", "group authorization", "access denied",
                            "this action is not available", "community token", "group token",
                            "error_code: 15", "no access to call this method",
                        ]):
                            msg = f"Нет прав на загрузку {item_type}. Получите пользовательский токен в Настройках (кнопка «Получить токен ВК»)"
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
                    "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, 0)",
                    (post_dict.get("author_id", 1), notif_msg, notif_type),
                )
                conn.commit()
            except Exception as e:
                vk_error = str(e)
                c.execute(
                    "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, 0)",
                    (post_dict.get("author_id", 1), f"Ошибка публикации в VK: {vk_error}", "error"),
                )
                conn.commit()

    tg_message_ids: list = []
    tg_error = None
    if "telegram" in platforms:
        c.execute("SELECT bot_token, chat_id FROM tg_settings WHERE id=1")
        tg = decrypt_row_secret(c.fetchone(), "bot_token")
        if tg:
            try:
                tg_message = f"{post_dict['title']}\n\n{post_dict['content']}" if post_dict.get("title") else post_dict.get("content", "")
                backend_base = os.getenv("BACKEND_URL", "https://backend-production-30d6.up.railway.app").rstrip("/")
                tg_message_ids = tg_send_post(
                    tg["bot_token"], tg["chat_id"], tg_message,
                    post_dict.get("media") or [], backend_base,
                )
                c.execute(
                    "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, 0)",
                    (post_dict.get("author_id", 1),
                     f"Пост «{post_dict['title']}» опубликован в Telegram", "success"),
                )
                conn.commit()
            except Exception as e:
                tg_error = str(e)
                c.execute(
                    "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, 0)",
                    (post_dict.get("author_id", 1),
                     f"Ошибка публикации в Telegram: {tg_error}", "error"),
                )
                conn.commit()

    if vk_post_id is not None:
        c.execute("UPDATE posts SET vk_post_id=%s WHERE id=%s", (str(vk_post_id), post_id))
    if tg_message_ids:
        c.execute("UPDATE posts SET tg_message_ids=%s WHERE id=%s", (json.dumps(tg_message_ids), post_id))
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
    if tg_message_ids:
        result["tg_message_ids"] = tg_message_ids
    if tg_error is not None:
        result["tg_error"] = tg_error
    return result


# ── Group-scoped Posts ──────────────────────────────────────────────────────

@router.get("/api/groups/{gid}/posts")
def get_group_posts(
    gid: int,
    q: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
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
    query += " ORDER BY p.created_at DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    c.execute(query, params)
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM posts WHERE group_id=%s", (gid,))
    total = c.fetchone()["count"]
    conn.close()
    return {"posts": [row_to_dict(r) for r in rows], "total": total}


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
         json.dumps([m.dict() for m in body.media]), gid),
    )
    pid = c.fetchone()["id"]
    conn.commit()
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    row = c.fetchone()
    conn.close()
    return row_to_dict(row)


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
    conn.close()
    if not row:
        raise HTTPException(404, "Пост не найден")
    return row_to_dict(row)


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
        params.append(json.dumps([m.dict() for m in body.media]))
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
    conn.close()
    return row_to_dict(row)


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
    c.execute("SELECT * FROM posts WHERE id=%s AND group_id=%s", (post_id, gid))
    post = c.fetchone()
    if not post:
        conn.close()
        raise HTTPException(404, "Пост не найден")
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute(
        "UPDATE posts SET status='published',published_at=%s,views=0,reactions=0,comments=0,shares=0 WHERE id=%s",
        (now, post_id),
    )
    conn.commit()
    post_dict = row_to_dict(post)
    vk_post_id = None
    vk_error = None
    photo_errors: list = []
    platforms = post_dict.get("platforms", [])
    backend_base = os.getenv("BACKEND_URL", "https://backend-production-30d6.up.railway.app").rstrip("/")
    if "vk" in platforms:
        c.execute("SELECT group_id, access_token FROM vk_settings WHERE workspace_id=%s", (gid,))
        vk = decrypt_row_secret(c.fetchone(), "access_token")
        if vk:
            try:
                message = f"{post_dict['title']}\n\n{post_dict['content']}"
                attachments = []
                for item in (post_dict.get("media") or []):
                    item_type = item.get("type")
                    if item_type not in ("image", "video", "doc"):
                        continue
                    fname = os.path.basename(item["url"])
                    orig_name = item.get("filename") or fname
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    try:
                        if os.path.exists(fpath):
                            with open(fpath, "rb") as f:
                                file_data = f.read()
                        else:
                            file_url = f"{backend_base}{item['url']}"
                            resp = http_requests.get(file_url, timeout=120)
                            resp.raise_for_status()
                            file_data = resp.content
                        if item_type == "image":
                            att = vk_upload_photo_to_wall(vk["access_token"], vk["group_id"], file_data, fname)
                        elif item_type == "video":
                            att = vk_upload_video_to_wall(
                                vk["access_token"], vk["group_id"], file_data, fname,
                                title=post_dict.get("title", ""),
                                description=post_dict.get("content", ""),
                            )
                        else:
                            att = vk_upload_doc_to_wall(
                                vk["access_token"], vk["group_id"], file_data, orig_name,
                                title=post_dict.get("title", "") or orig_name,
                            )
                        attachments.append(att)
                    except Exception as media_err:
                        msg = str(media_err)
                        if any(kw in msg.lower() for kw in [
                            "unavailable with group auth", "group authorization", "access denied",
                            "this action is not available", "community token", "group token",
                            "error_code: 15", "no access to call this method",
                        ]):
                            msg = f"Нет прав на загрузку {item_type}. Получите пользовательский токен в Настройках"
                        photo_errors.append(msg)
                vk_post_id = vk_wall_post(vk["access_token"], vk["group_id"], message, attachments)
            except Exception as e:
                vk_error = str(e)

    tg_message_ids: list = []
    tg_error = None
    if "telegram" in platforms:
        c.execute("SELECT bot_token, chat_id FROM tg_settings WHERE workspace_id=%s", (gid,))
        tg = decrypt_row_secret(c.fetchone(), "bot_token")
        if tg:
            try:
                tg_message = f"{post_dict['title']}\n\n{post_dict['content']}" if post_dict.get("title") else post_dict.get("content", "")
                tg_message_ids = tg_send_post(
                    tg["bot_token"], tg["chat_id"], tg_message,
                    post_dict.get("media") or [], backend_base,
                )
            except Exception as e:
                tg_error = str(e)

    if vk_post_id is not None:
        c.execute("UPDATE posts SET vk_post_id=%s WHERE id=%s", (str(vk_post_id), post_id))
    if tg_message_ids:
        c.execute("UPDATE posts SET tg_message_ids=%s WHERE id=%s", (json.dumps(tg_message_ids), post_id))
    conn.commit()

    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    row = c.fetchone()
    conn.close()
    result = row_to_dict(row)
    result["vk_post_id"] = vk_post_id
    result["vk_error"] = vk_error
    result["photo_errors"] = photo_errors
    result["tg_message_ids"] = tg_message_ids
    result["tg_error"] = tg_error
    return result


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
                    c.execute(
                        "UPDATE posts SET views=%s, reactions=%s, comments=%s, shares=%s, vk_stats_updated_at=%s WHERE vk_post_id=%s AND status='published'",
                        (views, reactions, comments, shares,
                         datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"), vp_id),
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
                    "UPDATE posts SET views=%s, reactions=%s, comments=%s, shares=%s, vk_stats_updated_at=%s WHERE vk_post_id=%s AND group_id=%s AND status='published'",
                    (views, reactions, comments, shares,
                     datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"), vp_id, gid),
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
    conn.close()
    return [row_to_dict(r) for r in rows]


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
