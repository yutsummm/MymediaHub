
import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, Request

import audit
from models import TgSettingsSave, VkOAuthExchange, VkSettingsSave
from utils import (
    app_now,
    encrypt_secret,
    get_current_user_id,
    get_db,
    require_admin,
    require_group_member,
    tg_get_chat_title,
    vk_get_group_name,
)

router = APIRouter()


# ── Ядро: одно на глобальные и групповые настройки ──────────────────────────
# Глобальные и групповые ручки были почти дословными копиями, и копии уже
# разъехались: глобальное подключение Telegram отвергало неверный токен, а
# групповое молча проглатывало любую ошибку и сохраняло настройку. Теперь
# логика одна, а «где хранить» сведено к паре (условие, workspace_id).
#
# Строка с id=1 — легаси одиночного воркспейса: на неё работают пользователи
# без группы. Удалять её нельзя, но и дублировать код ради неё незачем.


def _scope(gid: int | None) -> tuple[str, list]:
    return ("id=1", []) if gid is None else ("workspace_id=%s", [gid])


def _require_rights(conn, user_id: int, gid: int | None) -> None:
    """Глобальные настройки — админ системы, групповые — админ группы."""
    if gid is None:
        require_admin(user_id, conn)
        return
    if require_group_member(gid, user_id, conn) != "admin":
        conn.close()
        raise HTTPException(403, "Только администратор может изменять настройки")


def _read_settings(conn, table: str, columns: str, gid: int | None) -> dict:
    where, params = _scope(gid)
    c = conn.cursor()
    c.execute(f"SELECT {columns} FROM {table} WHERE {where}", params)  # noqa: S608 — имена свои
    row = c.fetchone()
    if not row:
        return {"connected": False}
    return {**dict(row), "connected": True}


def _upsert(conn, table: str, gid: int | None, values: dict) -> None:
    where, params = _scope(gid)
    c = conn.cursor()
    c.execute(f"SELECT 1 FROM {table} WHERE {where}", params)  # noqa: S608
    if c.fetchone():
        assignments = ", ".join(f"{k}=%s" for k in values)
        c.execute(f"UPDATE {table} SET {assignments} WHERE {where}",  # noqa: S608
                  list(values.values()) + params)
    else:
        keyed = dict(values)
        keyed["id" if gid is None else "workspace_id"] = 1 if gid is None else gid
        cols = ", ".join(keyed)
        marks = ", ".join(["%s"] * len(keyed))
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(keyed.values()))  # noqa: S608
    conn.commit()


def _delete_settings(conn, table: str, gid: int | None, actor_id: int, request=None) -> dict:
    """
    Отключает интеграцию. Отключение оставляет след: после него посты
    перестают уходить в паблик, а по интерфейсу это выглядит как «ничего не
    происходит» — вопрос «кто отключил» возникает обязательно.
    """
    where, params = _scope(gid)
    c = conn.cursor()
    c.execute(f"DELETE FROM {table} WHERE {where}", params)  # noqa: S608
    audit.record(
        conn, actor_id, audit.INTEGRATION_DISCONNECTED,
        object_type=table, group_id=gid,
        object_label="ВКонтакте" if table == "vk_settings" else "Telegram",
        request=request,
    )
    conn.commit()
    return {"connected": False}


def _vk_group_name(access_token: str, group_id: str) -> str:
    """Название паблика. Недоступное имя — не повод отказывать в подключении."""
    try:
        return vk_get_group_name(access_token, group_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        return f"Группа {group_id.lstrip('-')}"


def _tg_chat_title(bot_token: str, chat_id: str) -> str:
    """
    Название чата. Токен проверяем всерьёз: сохранить неверный — значит потом
    молча не публиковать. А вот недоступное название не повод отказывать —
    у закрытых каналов getChat может не отвечать по другим причинам.
    """
    try:
        return tg_get_chat_title(bot_token, chat_id)
    except ValueError as e:
        raise HTTPException(400, f"Telegram отклонил подключение: {e}")
    except Exception:
        return chat_id


def _save_vk(conn, gid: int | None, group_id: str, access_token: str) -> dict:
    clean_id = group_id.lstrip("-")
    group_name = _vk_group_name(access_token, group_id)
    now = app_now()
    _upsert(conn, "vk_settings", gid, {
        "group_id": clean_id,
        "access_token": encrypt_secret(access_token),
        "group_name": group_name,
        "connected_at": now,
    })
    return {"connected": True, "group_id": clean_id, "group_name": group_name, "connected_at": now}


def _save_tg(conn, gid: int | None, bot_token: str, chat_id: str) -> dict:
    chat_title = _tg_chat_title(bot_token, chat_id)
    now = app_now()
    _upsert(conn, "tg_settings", gid, {
        "bot_token": encrypt_secret(bot_token),
        "chat_id": chat_id,
        "chat_title": chat_title,
        "connected_at": now,
    })
    return {"connected": True, "chat_id": chat_id, "chat_title": chat_title, "connected_at": now}


VK_COLUMNS = "group_id, group_name, connected_at"
TG_COLUMNS = "chat_id, chat_title, connected_at"


# ── VK ───────────────────────────────────────────────────────────────────────

@router.get("/api/settings/vk")
def get_vk_settings(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
        return _read_settings(conn, "vk_settings", VK_COLUMNS, None)
    finally:
        conn.close()


@router.post("/api/settings/vk")
def save_vk_settings(body: VkSettingsSave, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
        return _save_vk(conn, None, body.group_id, body.access_token)
    finally:
        conn.close()


@router.delete("/api/settings/vk")
def delete_vk_settings(user_id: int = Depends(get_current_user_id), request: Request = None):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
        return _delete_settings(conn, "vk_settings", None, user_id, request)
    finally:
        conn.close()


@router.get("/api/groups/{gid}/settings/vk")
def get_group_vk_settings(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        return _read_settings(conn, "vk_settings", VK_COLUMNS, gid)
    finally:
        conn.close()


@router.post("/api/groups/{gid}/settings/vk")
def save_group_vk_settings(gid: int, body: VkSettingsSave, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, gid)
        return _save_vk(conn, gid, body.group_id, body.access_token)
    finally:
        conn.close()


@router.delete("/api/groups/{gid}/settings/vk")
def delete_group_vk_settings(
    gid: int, user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    try:
        _require_rights(conn, user_id, gid)
        return _delete_settings(conn, "vk_settings", gid, user_id, request)
    finally:
        conn.close()


@router.post("/api/vk/oauth-exchange")
def vk_oauth_exchange(body: VkOAuthExchange, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
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
            raise HTTPException(
                400, data.get("error_description") or data.get("error", "OAuth ошибка")
            )
        access_token = data.get("access_token")
        if not access_token:
            raise HTTPException(400, "Токен не получен от VK")
        return _save_vk(conn, None, body.group_id, access_token)
    finally:
        conn.close()


# ── Telegram ─────────────────────────────────────────────────────────────────

@router.get("/api/settings/telegram")
def get_tg_settings(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
        return _read_settings(conn, "tg_settings", TG_COLUMNS, None)
    finally:
        conn.close()


@router.post("/api/settings/telegram")
def save_tg_settings(body: TgSettingsSave, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
        return _save_tg(conn, None, body.bot_token, body.chat_id)
    finally:
        conn.close()


@router.delete("/api/settings/telegram")
def delete_tg_settings(user_id: int = Depends(get_current_user_id), request: Request = None):
    conn = get_db()
    try:
        _require_rights(conn, user_id, None)
        return _delete_settings(conn, "tg_settings", None, user_id, request)
    finally:
        conn.close()


@router.get("/api/groups/{gid}/settings/telegram")
def get_group_tg_settings(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        return _read_settings(conn, "tg_settings", TG_COLUMNS, gid)
    finally:
        conn.close()


@router.post("/api/groups/{gid}/settings/telegram")
def save_group_tg_settings(gid: int, body: TgSettingsSave, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        _require_rights(conn, user_id, gid)
        return _save_tg(conn, gid, body.bot_token, body.chat_id)
    finally:
        conn.close()


@router.delete("/api/groups/{gid}/settings/telegram")
def delete_group_tg_settings(
    gid: int, user_id: int = Depends(get_current_user_id), request: Request = None,
):
    conn = get_db()
    try:
        _require_rights(conn, user_id, gid)
        return _delete_settings(conn, "tg_settings", gid, user_id, request)
    finally:
        conn.close()
