"""
Сбор статистики Telegram.

Синхронизации не было вовсе. Теперь реакции вычитываются из потока апдейтов и
ложатся в свою строку post_stats — не трогая цифры ВК.

Просмотры Bot API не отдаёт ни одним методом (нужен MTProto), поэтому по ним
по-прежнему честное «нет данных»: это проверяется отдельно, чтобы никто потом
не подставил туда чужое число.
"""
import json

from conftest import auth

import telegram_stats
from stats import stats_for_posts
from utils import encrypt_secret, get_db


def make_tg_settings(workspace_id=None, chat_id="@test_channel", offset=None) -> int:
    """
    Чистим таблицу целиком: настройки от других тестов тоже попали бы в обход и
    обработали бы тот же апдейт по второму разу.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM tg_settings")
    c.execute(
        "INSERT INTO tg_settings (bot_token, chat_id, workspace_id, updates_offset) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (encrypt_secret("111:БотовыйТокен"), chat_id, workspace_id, offset),
    )
    sid = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return sid


def published_with_tg(client, group, message_ids: list[int]) -> int:
    gid = group["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "В телеграме", "content": "т", "platforms": ["telegram"]},
        headers=auth(group["token"]),
    ).json()["id"]
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE posts SET status='published', tg_message_ids=%s WHERE id=%s",
        (json.dumps(message_ids), pid),
    )
    conn.commit()
    conn.close()
    return pid


def reaction_update(update_id: int, chat_id: str, message_id: int, counts: list[int]) -> dict:
    return {
        "update_id": update_id,
        "message_reaction_count": {
            "chat": {"id": chat_id},
            "message_id": message_id,
            "reactions": [{"type": {"emoji": "👍"}, "total_count": n} for n in counts],
        },
    }


def stats_of(pid: int, platform: str) -> dict:
    """Строка статистики по площадке. Её отсутствие — уже провал теста."""
    conn = get_db()
    rows = stats_for_posts(conn, [pid]).get(pid, [])
    conn.close()
    row = next((r for r in rows if r["platform"] == platform), None)
    assert row is not None, f"нет статистики {platform} у поста {pid}"
    return row


# ── Разбор апдейтов ──────────────────────────────────────────────────────────

def test_reactions_land_on_the_right_post(client, group_with_post, monkeypatch):
    """Ровно то, чего не было: цифры из Telegram доезжают до поста."""
    gid = group_with_post["group_id"]
    sid = make_tg_settings(workspace_id=gid, chat_id="-100500")
    pid = published_with_tg(client, group_with_post, [42])

    monkeypatch.setattr(
        telegram_stats, "fetch_updates",
        lambda token, offset: [reaction_update(1, "-100500", 42, [3, 4])],
    )
    assert telegram_stats.collect_telegram_stats() == 1
    assert stats_of(pid, "telegram")["reactions"] == 7, "суммируются все виды реакций"
    assert sid


def test_telegram_does_not_touch_vk_numbers(client, group_with_post, monkeypatch):
    """Главный смысл разделения: одна площадка не затирает другую."""
    from stats import save_platform_stats

    gid = group_with_post["group_id"]
    make_tg_settings(workspace_id=gid, chat_id="-100500")
    pid = published_with_tg(client, group_with_post, [7])

    conn = get_db()
    save_platform_stats(conn, pid, "vk", views=1000, reactions=50)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        telegram_stats, "fetch_updates",
        lambda token, offset: [reaction_update(1, "-100500", 7, [2])],
    )
    telegram_stats.collect_telegram_stats()

    assert stats_of(pid, "vk")["reactions"] == 50, "цифры ВК должны остаться нетронутыми"
    assert stats_of(pid, "vk")["views"] == 1000
    assert stats_of(pid, "telegram")["reactions"] == 2


def test_views_are_never_invented(client, group_with_post, monkeypatch):
    """
    Bot API просмотры не отдаёт. Значит в строке Telegram их быть не должно —
    ни нуля, ни чужого числа.
    """
    gid = group_with_post["group_id"]
    make_tg_settings(workspace_id=gid, chat_id="-100500")
    pid = published_with_tg(client, group_with_post, [9])
    monkeypatch.setattr(
        telegram_stats, "fetch_updates",
        lambda token, offset: [reaction_update(1, "-100500", 9, [5])],
    )
    telegram_stats.collect_telegram_stats()
    assert stats_of(pid, "telegram")["views"] is None


def test_unknown_message_is_skipped(client, group_with_post, monkeypatch):
    gid = group_with_post["group_id"]
    make_tg_settings(workspace_id=gid, chat_id="-100500")
    published_with_tg(client, group_with_post, [11])
    monkeypatch.setattr(
        telegram_stats, "fetch_updates",
        lambda token, offset: [reaction_update(1, "-100500", 999999, [5])],
    )
    assert telegram_stats.collect_telegram_stats() == 0


def test_message_id_is_matched_exactly(client, group_with_post, monkeypatch):
    """
    tg_message_ids — JSON-строка, и поиск идёт через LIKE. Без разбора списка
    апдейт про сообщение 12 прилип бы к посту с сообщением 123.
    """
    gid = group_with_post["group_id"]
    make_tg_settings(workspace_id=gid, chat_id="-100500")
    published_with_tg(client, group_with_post, [123])
    monkeypatch.setattr(
        telegram_stats, "fetch_updates",
        lambda token, offset: [reaction_update(1, "-100500", 12, [9])],
    )
    assert telegram_stats.collect_telegram_stats() == 0, "12 не должно совпасть со 123"


# ── Смещение ─────────────────────────────────────────────────────────────────

def test_offset_advances_so_updates_are_not_reread(client, group_with_post, monkeypatch):
    gid = group_with_post["group_id"]
    sid = make_tg_settings(workspace_id=gid, chat_id="-100500")
    published_with_tg(client, group_with_post, [21])

    monkeypatch.setattr(
        telegram_stats, "fetch_updates",
        lambda token, offset: [reaction_update(77, "-100500", 21, [1])],
    )
    telegram_stats.collect_telegram_stats()

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT updates_offset FROM tg_settings WHERE id=%s", (sid,))
    offset = c.fetchone()["updates_offset"]
    conn.close()
    assert offset == 78, "смещение должно уйти за последний обработанный апдейт"


def test_saved_offset_is_passed_to_telegram(client, group_with_post, monkeypatch):
    gid = group_with_post["group_id"]
    make_tg_settings(workspace_id=gid, chat_id="-100500", offset=500)
    seen = {}

    def fake(token, offset):
        seen["offset"] = offset
        return []

    monkeypatch.setattr(telegram_stats, "fetch_updates", fake)
    telegram_stats.collect_telegram_stats()
    assert seen["offset"] == 500


# ── Устойчивость ─────────────────────────────────────────────────────────────

def test_telegram_error_does_not_break_the_run(client, group_with_post, monkeypatch):
    """Недоступный Telegram не должен ронять фоновый цикл."""
    gid = group_with_post["group_id"]
    make_tg_settings(workspace_id=gid, chat_id="-100500")

    def boom(token, offset):
        raise RuntimeError("Telegram недоступен")

    monkeypatch.setattr(telegram_stats, "fetch_updates", boom)
    assert telegram_stats.collect_telegram_stats() == 0


def test_no_settings_means_no_work(monkeypatch):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM tg_settings")
    conn.commit()
    conn.close()
    monkeypatch.setattr(telegram_stats, "fetch_updates", lambda *a: 1 / 0)
    assert telegram_stats.collect_telegram_stats() == 0


def test_only_reaction_updates_are_requested():
    """
    Просим у Telegram только реакции: широкий allowed_updates вычитал бы и
    съедал чужие апдейты, если у бота появится своя логика.
    """
    assert telegram_stats.ALLOWED_UPDATES == ["message_reaction_count"]
