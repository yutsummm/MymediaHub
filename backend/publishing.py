"""
Механика публикации поста в соцсети — одна на всех.

Раньше она была скопирована в две ручки (глобальную и групповую), а с
появлением планировщика появилась бы третья копия. Здесь всё в одном месте:
и ручки, и автопубликация зовут perform_publish.
"""
import os

import requests as http_requests
from psycopg2.extras import Json

from stats import serialize_post
from utils import (
    UPLOAD_DIR,
    app_now,
    decrypt_row_secret,
    row_to_dict,
    tg_send_post,
    upload_filename,
    vk_upload_doc_to_wall,
    vk_upload_photo_to_wall,
    vk_upload_video_to_wall,
    vk_wall_post,
)

# Ошибки ВК, которые на деле означают «нужен пользовательский токен»
_VK_TOKEN_HINTS = (
    "unavailable with group auth", "group authorization", "access denied",
    "this action is not available", "community token", "group token",
    "error_code: 15", "no access to call this method",
)


def backend_base() -> str:
    return os.getenv(
        "BACKEND_URL", "https://backend-production-30d6.up.railway.app"
    ).rstrip("/")


def _notify(c, user_id, message: str, kind: str) -> None:
    c.execute(
        "INSERT INTO notifications (user_id, message, type, is_read) VALUES (%s, %s, %s, 0)",
        (user_id, message, kind),
    )


def _media_bytes(item: dict) -> bytes:
    """Файл с диска, а если его там нет — по подписанной ссылке."""
    fpath = os.path.join(UPLOAD_DIR, upload_filename(item["url"]))
    if os.path.exists(fpath):
        with open(fpath, "rb") as f:
            return f.read()
    resp = http_requests.get(f"{backend_base()}{item['url']}", timeout=120)
    resp.raise_for_status()
    return resp.content


def _publish_to_vk(c, post: dict, settings: dict) -> tuple[int | None, list[str]]:
    """Возвращает (id записи на стене, ошибки по отдельным файлам)."""
    photo_errors: list[str] = []
    attachments: list[str] = []
    token, group = settings["access_token"], settings["group_id"]

    for item in (post.get("media") or []):
        item_type = item.get("type")
        if item_type not in ("image", "video", "doc"):
            continue
        fname = upload_filename(item["url"])
        orig_name = item.get("filename") or fname
        try:
            data = _media_bytes(item)
            if item_type == "image":
                attachments.append(vk_upload_photo_to_wall(token, group, data, fname))
            elif item_type == "video":
                attachments.append(vk_upload_video_to_wall(
                    token, group, data, fname,
                    title=post.get("title", ""), description=post.get("content", ""),
                ))
            else:
                attachments.append(vk_upload_doc_to_wall(
                    token, group, data, orig_name,
                    title=post.get("title", "") or orig_name,
                ))
        except Exception as media_err:
            msg = str(media_err)
            if any(kw in msg.lower() for kw in _VK_TOKEN_HINTS):
                msg = (
                    f"Нет прав на загрузку {item_type}. Получите пользовательский "
                    "токен в Настройках (кнопка «Получить токен ВК»)"
                )
            photo_errors.append(msg)

    message = f"{post['title']}\n\n{post['content']}"
    return vk_wall_post(token, group, message, attachments), photo_errors


def perform_publish(conn, post_row, group_id: int | None = None) -> dict:
    """
    Публикует пост и проставляет отметки в базе.

    group_id=None — легаси-настройки одиночного воркспейса (строка с id=1),
    иначе берутся настройки конкретной группы.

    Соединение не закрывает: вызывающий сам решает, что делать дальше.
    """
    c = conn.cursor()
    post = row_to_dict(post_row)
    post_id = post["id"]
    author_id = post.get("author_id") or 1
    title = post.get("title") or "без названия"

    c.execute(
        "UPDATE posts SET status='published', published_at=%s WHERE id=%s",
        (app_now(), post_id),
    )
    conn.commit()

    platforms = post.get("platforms") or []
    vk_post_id = None
    vk_error = None
    photo_errors: list[str] = []
    tg_message_ids: list[int] = []
    tg_error = None

    if "vk" in platforms:
        if group_id is None:
            c.execute("SELECT group_id, access_token FROM vk_settings WHERE id=1")
        else:
            c.execute(
                "SELECT group_id, access_token FROM vk_settings WHERE workspace_id=%s",
                (group_id,),
            )
        vk = decrypt_row_secret(c.fetchone(), "access_token")
        if vk:
            try:
                vk_post_id, photo_errors = _publish_to_vk(c, post, vk)
                if photo_errors:
                    _notify(c, author_id, (
                        f"Пост «{title}» опубликован в ВКонтакте, но "
                        f"{len(photo_errors)} файлов не загружено: {photo_errors[0]}"
                    ), "warning")
                else:
                    _notify(c, author_id, f"Пост «{title}» опубликован в группу ВКонтакте", "success")
                conn.commit()
            except Exception as e:
                vk_error = str(e)
                _notify(c, author_id, f"Ошибка публикации в VK: {vk_error}", "error")
                conn.commit()

    if "telegram" in platforms:
        if group_id is None:
            c.execute("SELECT bot_token, chat_id FROM tg_settings WHERE id=1")
        else:
            c.execute(
                "SELECT bot_token, chat_id FROM tg_settings WHERE workspace_id=%s",
                (group_id,),
            )
        tg = decrypt_row_secret(c.fetchone(), "bot_token")
        if tg:
            try:
                text = f"{title}\n\n{post['content']}" if post.get("title") else post.get("content", "")
                tg_message_ids = tg_send_post(
                    tg["bot_token"], tg["chat_id"], text,
                    post.get("media") or [], backend_base(),
                )
                _notify(c, author_id, f"Пост «{title}» опубликован в Telegram", "success")
                conn.commit()
            except Exception as e:
                tg_error = str(e)
                _notify(c, author_id, f"Ошибка публикации в Telegram: {tg_error}", "error")
                conn.commit()

    if vk_post_id is not None:
        c.execute("UPDATE posts SET vk_post_id=%s WHERE id=%s", (str(vk_post_id), post_id))
    if tg_message_ids:
        c.execute(
            "UPDATE posts SET tg_message_ids=%s WHERE id=%s",
            (Json(tg_message_ids), post_id),
        )
    # Ошибку храним в самом посте: уведомление можно смахнуть и не найти причину
    problems = [p for p in (vk_error, tg_error) if p]
    c.execute(
        "UPDATE posts SET publish_error=%s WHERE id=%s",
        ("; ".join(problems) or None, post_id),
    )
    conn.commit()

    c.execute("SELECT * FROM posts WHERE id=%s", (post_id,))
    result = serialize_post(conn, c.fetchone())
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
