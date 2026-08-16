"""
Сбор статистики Telegram.

Что здесь важно понимать сразу, потому что это ограничение самого Telegram,
а не проекта:

  * **Просмотры получить нельзя.** Bot API не отдаёт число просмотров сообщения
    ни одним методом. Оно доступно только через MTProto (клиентский протокол,
    messages.getMessagesViews), а это отдельная авторизация живым аккаунтом:
    api_id, api_hash и вход по коду из SMS. Пока такого доступа нет, просмотры
    по Telegram остаются честным «нет данных» — выдумывать их или показывать
    вместо них вконтактовские мы больше не станем.

  * **Реакции получить можно, но только вперёд.** Их нельзя запросить для уже
    вышедшего поста: Telegram присылает message_reaction_count как входящий
    апдейт в момент изменения. Поэтому мы их регулярно вычитываем и копим.
    Посты, опубликованные до включения сбора, чисел не получат.

Требования к боту: он должен быть администратором канала, иначе апдейтов
о реакциях не будет вовсе.
"""
import json
import os
import sys

import requests as http_requests
from psycopg2.extras import Json

from stats import save_platform_stats
from utils import decrypt_secret, get_db

TELEGRAM_STATS_ENABLED = os.getenv("TELEGRAM_STATS_ENABLED", "1").strip().lower() not in (
    "0", "false", "no",
)
# Апдейты живут у Telegram около суток, так что заглядывать надо чаще.
TELEGRAM_POLL_INTERVAL = int(os.getenv("TELEGRAM_POLL_SECONDS", "300"))
ALLOWED_UPDATES = ["message_reaction_count"]


def fetch_updates(bot_token: str, offset: int | None) -> list[dict]:
    """Забирает свежие апдейты о реакциях. Пустой список — тоже нормальный ответ."""
    params = {
        "timeout": 0,
        "allowed_updates": json.dumps(ALLOWED_UPDATES),
    }
    if offset is not None:
        params["offset"] = offset
    resp = http_requests.get(
        f"https://api.telegram.org/bot{bot_token}/getUpdates", params=params, timeout=30
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getUpdates: {data.get('description', data)}")
    return data.get("result", [])


def _reaction_total(update: dict) -> tuple[str, int, int] | None:
    """Из апдейта — (chat_id, message_id, сколько всего реакций)."""
    payload = update.get("message_reaction_count")
    if not payload:
        return None
    chat_id = payload.get("chat", {}).get("id")
    message_id = payload.get("message_id")
    if chat_id is None or message_id is None:
        return None
    total = sum(r.get("total_count", 0) for r in payload.get("reactions", []))
    return str(chat_id), message_id, total


def _match_post(c, chat_id: str, message_id: int, workspace_id) -> int | None:
    """
    Ищет пост по идентификатору сообщения.

    Через jsonb-содержание (@>), а не LIKE по строке: раньше апдейт про
    сообщение 12 совпадал бы и с постом, где лежит 123, и это приходилось
    отсеивать разбором списка в Python.
    """
    if workspace_id is None:
        c.execute(
            "SELECT id FROM posts WHERE tg_message_ids @> %s AND status='published'",
            (Json([message_id]),),
        )
    else:
        c.execute(
            "SELECT id FROM posts WHERE tg_message_ids @> %s "
            "AND group_id=%s AND status='published'",
            (Json([message_id]), workspace_id),
        )
    row = c.fetchone()
    return row["id"] if row else None


def collect_for_settings(conn, settings: dict) -> int:
    """
    Вычитывает реакции для одной подключённой пары «бот + чат».
    Возвращает, по скольким постам обновилась статистика.
    """
    bot_token = decrypt_secret(settings["bot_token"])
    if not bot_token:
        return 0
    updates = fetch_updates(bot_token, settings.get("updates_offset"))
    if not updates:
        return 0

    c = conn.cursor()
    touched = 0
    last_update_id = settings.get("updates_offset")
    for update in updates:
        last_update_id = update.get("update_id")
        parsed = _reaction_total(update)
        if not parsed:
            continue
        chat_id, message_id, total = parsed
        # Апдейт может прийти из чужого чата, если бот добавлен ещё куда-то
        if str(settings.get("chat_id") or "") not in ("", chat_id) and not str(
            settings.get("chat_id") or ""
        ).startswith("@"):
            continue
        post_id = _match_post(c, chat_id, message_id, settings.get("workspace_id"))
        if post_id is None:
            continue
        save_platform_stats(conn, post_id, "telegram", reactions=total)
        touched += 1

    if last_update_id is not None:
        # +1 — подтверждение: эти апдейты Telegram больше не отдаст
        c.execute(
            "UPDATE tg_settings SET updates_offset=%s WHERE id=%s",
            (last_update_id + 1, settings["id"]),
        )
    conn.commit()
    return touched


def collect_telegram_stats() -> int:
    """Проходит по всем подключённым Telegram-интеграциям."""
    conn = get_db()
    total = 0
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id, bot_token, chat_id, workspace_id, updates_offset FROM tg_settings"
        )
        for row in c.fetchall():
            try:
                total += collect_for_settings(conn, dict(row))
            except Exception as e:
                conn.rollback()
                print(f"⚠️   Telegram-статистика (настройка #{row['id']}): {e}", file=sys.stderr)
    finally:
        conn.close()
    if total:
        print(f"📊  реакции Telegram обновлены у постов: {total}")
    return total
