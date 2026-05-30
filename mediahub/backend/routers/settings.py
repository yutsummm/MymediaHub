from fastapi import APIRouter, HTTPException, Depends
from utils import (
    get_db, get_current_user_id, require_group_member,
    vk_get_group_name, tg_get_chat_title, VK_API_VERSION,
)
from models import VkSettingsSave, TgSettingsSave, VkOAuthExchange
from datetime import datetime
import requests as http_requests
import os

router = APIRouter()


# ── VK Settings ───────────────────────────────────────────────────────────────

@router.get("/api/settings/vk")
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


@router.post("/api/settings/vk")
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


@router.post("/api/vk/oauth-exchange")
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


@router.delete("/api/settings/vk")
def delete_vk_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM vk_settings WHERE id=1")
    conn.commit()
    conn.close()
    return {"connected": False}


# ── Group-scoped VK Settings ────────────────────────────────────────────────

@router.get("/api/groups/{gid}/settings/vk")
def get_group_vk_settings(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_group_member(gid, user_id, conn)
    c.execute("SELECT group_id, group_name, connected_at FROM vk_settings WHERE workspace_id=%s", (gid,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    d = dict(row)
    d["connected"] = True
    return d


@router.post("/api/groups/{gid}/settings/vk")
def save_group_vk_settings(gid: int, body: VkSettingsSave, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может изменять настройки")
    try:
        val_r = http_requests.get(
            "https://api.vk.com/method/users.get",
            params={"access_token": body.access_token, "v": VK_API_VERSION},
            timeout=10,
        )
        val_data = val_r.json()
        if "error" in val_data:
            conn.close()
            err_msg = val_data["error"].get("error_msg", "Ошибка VK")
            raise HTTPException(400, f"Недействительный токен ВК: {err_msg}")
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(400, f"Не удалось связаться с VK: {e}")
    clean_id = body.group_id.lstrip("-")
    group_name = f"Группа {clean_id}"
    try:
        group_name = vk_get_group_name(body.access_token, body.group_id)
    except Exception:
        pass
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute("SELECT workspace_id FROM vk_settings WHERE workspace_id=%s", (gid,))
    exists = c.fetchone()
    if exists:
        c.execute(
            "UPDATE vk_settings SET group_id=%s, access_token=%s, group_name=%s, connected_at=%s WHERE workspace_id=%s",
            (clean_id, body.access_token, group_name, now, gid),
        )
    else:
        c.execute(
            "INSERT INTO vk_settings (workspace_id, group_id, access_token, group_name, connected_at) VALUES (%s, %s, %s, %s, %s)",
            (gid, clean_id, body.access_token, group_name, now),
        )
    conn.commit()
    conn.close()
    return {"connected": True, "group_id": clean_id, "group_name": group_name, "connected_at": now}


@router.delete("/api/groups/{gid}/settings/vk")
def delete_group_vk_settings(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может удалять настройки")
    c.execute("DELETE FROM vk_settings WHERE workspace_id=%s", (gid,))
    conn.commit()
    conn.close()
    return {"connected": False}


# ── Telegram Settings ────────────────────────────────────────────────────────

@router.get("/api/settings/telegram")
def get_tg_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, chat_id, chat_title, connected_at FROM tg_settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    d = dict(row)
    d["connected"] = True
    return d


@router.post("/api/settings/telegram")
def save_tg_settings(body: TgSettingsSave):
    try:
        chat_title = tg_get_chat_title(body.bot_token, body.chat_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM tg_settings WHERE id=1")
    exists = c.fetchone()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if exists:
        c.execute(
            "UPDATE tg_settings SET bot_token=%s, chat_id=%s, chat_title=%s, connected_at=%s WHERE id=1",
            (body.bot_token, body.chat_id, chat_title, now),
        )
    else:
        c.execute(
            "INSERT INTO tg_settings (id, bot_token, chat_id, chat_title, connected_at) VALUES (1, %s, %s, %s, %s)",
            (body.bot_token, body.chat_id, chat_title, now),
        )
    conn.commit()
    conn.close()
    return {"connected": True, "chat_id": body.chat_id, "chat_title": chat_title, "connected_at": now}


@router.delete("/api/settings/telegram")
def delete_tg_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM tg_settings WHERE id=1")
    conn.commit()
    conn.close()
    return {"connected": False}


# ── Group-scoped Telegram Settings ──────────────────────────────────────────

@router.get("/api/groups/{gid}/settings/telegram")
def get_group_tg_settings(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    require_group_member(gid, user_id, conn)
    c.execute("SELECT chat_id, chat_title, connected_at FROM tg_settings WHERE workspace_id=%s", (gid,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"connected": False}
    d = dict(row)
    d["connected"] = True
    return d


@router.post("/api/groups/{gid}/settings/telegram")
def save_group_tg_settings(gid: int, body: TgSettingsSave, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может изменять настройки")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    chat_title = body.chat_id
    try:
        r = http_requests.get(
            f"https://api.telegram.org/bot{body.bot_token}/getChat",
            params={"chat_id": body.chat_id}, timeout=5,
        )
        data = r.json()
        if data.get("ok"):
            chat_title = data["result"].get("title") or data["result"].get("username") or body.chat_id
    except Exception:
        pass
    c.execute("SELECT workspace_id FROM tg_settings WHERE workspace_id=%s", (gid,))
    exists = c.fetchone()
    if exists:
        c.execute(
            "UPDATE tg_settings SET bot_token=%s, chat_id=%s, chat_title=%s, connected_at=%s WHERE workspace_id=%s",
            (body.bot_token, body.chat_id, chat_title, now, gid),
        )
    else:
        c.execute(
            "INSERT INTO tg_settings (workspace_id, bot_token, chat_id, chat_title, connected_at) VALUES (%s, %s, %s, %s, %s)",
            (gid, body.bot_token, body.chat_id, chat_title, now),
        )
    conn.commit()
    conn.close()
    return {"connected": True, "chat_id": body.chat_id, "chat_title": chat_title, "connected_at": now}


@router.delete("/api/groups/{gid}/settings/telegram")
def delete_group_tg_settings(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    c = conn.cursor()
    role = require_group_member(gid, user_id, conn)
    if role != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может удалять настройки")
    c.execute("DELETE FROM tg_settings WHERE workspace_id=%s", (gid,))
    conn.commit()
    conn.close()
    return {"connected": False}
