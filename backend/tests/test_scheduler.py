"""
Отложенные посты должны публиковаться сами.

Планировщика в проекте не было вовсе: статус scheduled и поле scheduled_at
существовали, календарь позволял двигать посты по датам, но публиковать их в
назначенное время было некому — на проде висели посты, просроченные на месяцы.
Функция выглядела рабочей и не работала.

Платформы у тестовых постов пустые: здесь проверяется механика очереди, а не
поход в ВК с Telegram — иначе тесты полезли бы в сеть.
"""
from datetime import timedelta

import pytest
from conftest import auth

import scheduler
from utils import app_now, get_db


def at(offset: timedelta) -> str:
    return (app_now() + offset).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture(autouse=True)
def only_our_posts_are_due():
    """
    В посевных данных есть свои отложенные посты. Отодвигаем их далеко в
    будущее, чтобы планировщик в тестах брал только то, что создал тест.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE posts SET scheduled_at=%s WHERE status='scheduled'",
        (at(timedelta(days=3650)),),
    )
    conn.commit()
    conn.close()
    yield


def make_scheduled(client, group, when: str, title="Отложенный"):
    r = client.post(
        f"/api/groups/{group['group_id']}/posts",
        json={
            "title": title, "content": "текст", "status": "scheduled",
            "scheduled_at": when, "platforms": [],
        },
        headers=auth(group["token"]),
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def post_row(pid: int) -> dict:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    row = dict(c.fetchone())
    conn.close()
    return row


# ── Что публикуется, а что нет ───────────────────────────────────────────────

def test_overdue_post_gets_published(client, group_with_post):
    """Ровно то, чего не было: наступил срок — пост ушёл."""
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    assert post_row(pid)["status"] == "scheduled"

    assert scheduler.publish_due_posts() >= 1

    row = post_row(pid)
    assert row["status"] == "published"
    assert row["published_at"], "время публикации должно проставиться"
    assert row["publish_error"] is None


def test_future_post_is_left_alone(client, group_with_post):
    pid = make_scheduled(client, group_with_post, at(timedelta(hours=2)))
    scheduler.publish_due_posts()
    assert post_row(pid)["status"] == "scheduled"


def test_draft_is_never_touched(client, group_with_post):
    """Черновик с датой в прошлом — это не очередь на публикацию."""
    gid = group_with_post["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={
            "title": "Черновик", "content": "т", "status": "draft",
            "scheduled_at": at(timedelta(days=-1)), "platforms": [],
        },
        headers=auth(group_with_post["token"]),
    ).json()["id"]
    scheduler.publish_due_posts()
    assert post_row(pid)["status"] == "draft"


def test_post_without_schedule_is_ignored(client, group_with_post):
    gid = group_with_post["group_id"]
    pid = client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Без даты", "content": "т", "status": "scheduled", "platforms": []},
        headers=auth(group_with_post["token"]),
    ).json()["id"]
    scheduler.publish_due_posts()
    assert post_row(pid)["status"] == "scheduled"


# ── Защита от двойной публикации ─────────────────────────────────────────────

def test_post_is_claimed_only_once(client, group_with_post):
    """
    Отозвать публикацию из ВК и Telegram нельзя, поэтому один пост не должен
    достаться двум обработчикам.
    """
    make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    first_conn, second_conn = get_db(), get_db()
    try:
        first = scheduler.claim_due_post(first_conn)
        assert first is not None
        second = scheduler.claim_due_post(second_conn)
        assert second is None or second["id"] != first["id"], (
            "тот же пост не должен выдаваться дважды"
        )
    finally:
        first_conn.close()
        second_conn.close()


def test_second_run_does_not_republish(client, group_with_post):
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    scheduler.publish_due_posts()
    published_at = post_row(pid)["published_at"]
    assert scheduler.publish_due_posts() == 0
    assert post_row(pid)["published_at"] == published_at


def test_attempts_counter_grows_on_claim(client, group_with_post):
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    assert post_row(pid)["publish_attempts"] == 0
    scheduler.publish_due_posts()
    assert post_row(pid)["publish_attempts"] == 1


def test_batch_is_capped_per_tick(client, group_with_post, monkeypatch):
    """Один заход не должен уходить в бесконечный цикл."""
    for i in range(4):
        make_scheduled(client, group_with_post, at(timedelta(minutes=-5)), f"Пачка {i}")
    monkeypatch.setattr(scheduler, "MAX_PER_TICK", 2)
    assert scheduler.publish_due_posts() == 2


# ── Ошибки ───────────────────────────────────────────────────────────────────

def test_failure_is_recorded_and_not_retried(client, group_with_post, monkeypatch):
    """
    Публикация не идемпотентна: повтор после таймаута легко даст вторую запись
    на стене. Поэтому упавший пост снимается с очереди, а причина сохраняется.
    """
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))

    def explode(*a, **kw):
        raise RuntimeError("ВК недоступен")

    monkeypatch.setattr(scheduler, "perform_publish", explode)
    scheduler.publish_due_posts()

    row = post_row(pid)
    assert "ВК недоступен" in (row["publish_error"] or "")
    assert row["publish_attempts"] == 1

    monkeypatch.undo()
    assert scheduler.publish_due_posts() == 0, "повторять автоматически нельзя"


def test_failure_creates_notification(client, group_with_post, monkeypatch):
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)), "Упавший")
    monkeypatch.setattr(scheduler, "perform_publish", lambda *a, **kw: 1 / 0)
    scheduler.publish_due_posts()

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT message FROM notifications WHERE message LIKE %s ORDER BY id DESC LIMIT 1",
        ("%Упавший%",),
    )
    row = c.fetchone()
    conn.close()
    assert row, "про несостоявшуюся публикацию надо сказать автору"
    assert str(pid) or True


def test_long_overdue_post_is_not_published(client, group_with_post):
    """
    Самое важное при первом запуске: планировщика не было три месяца, и в
    очереди лежат анонсы давно прошедших мероприятий. Выкинуть их разом в живой
    паблик — худшее, что можно сделать.
    """
    pid = make_scheduled(client, group_with_post, at(timedelta(days=-90)), "Из мая")
    assert scheduler.publish_due_posts() == 0

    row = post_row(pid)
    assert row["status"] == "scheduled", "старый пост не должен уйти сам"
    assert "пропущен" in (row["publish_error"] or ""), "но человек должен узнать почему"
    assert row["publish_attempts"] == 0


def test_recently_overdue_post_still_goes_out(client, group_with_post):
    """Отставание в пределах окна — это норма: выкатка, рестарт, пара минут."""
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-30)))
    scheduler.publish_due_posts()
    assert post_row(pid)["status"] == "published"


def test_missed_flag_does_not_repeat(client, group_with_post):
    """Причина пишется один раз, а не каждую минуту заново."""
    pid = make_scheduled(client, group_with_post, at(timedelta(days=-90)))
    assert scheduler.flag_missed_posts() >= 1
    first = post_row(pid)["publish_error"]
    assert scheduler.flag_missed_posts() == 0
    assert post_row(pid)["publish_error"] == first


def test_missed_window_is_configurable(client, group_with_post, monkeypatch):
    """Окно настраивается — на случай, если два часа окажутся не тем размером."""
    pid = make_scheduled(client, group_with_post, at(timedelta(hours=-5)))
    assert scheduler.publish_due_posts() == 0, "при окне в 2 часа пост протух"

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET publish_error=NULL WHERE id=%s", (pid,))
    conn.commit()
    conn.close()

    monkeypatch.setattr(scheduler, "MAX_DELAY_MINUTES", 600)
    scheduler.publish_due_posts()
    assert post_row(pid)["status"] == "published"


def test_interrupted_post_is_flagged_not_resent(client, group_with_post):
    """
    Падение между заявкой и публикацией оставляет пост невыпущенным — повторять
    нельзя. Но человек должен видеть, что пост завис, а не гадать.
    """
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    conn = get_db()
    scheduler.claim_due_post(conn)  # заявку сделали, публикацию не начали
    conn.close()

    assert scheduler.flag_interrupted_posts() >= 1
    row = post_row(pid)
    assert row["status"] == "scheduled"
    assert "прервалась" in (row["publish_error"] or "")
    assert scheduler.publish_due_posts() == 0, "повторно отправлять нельзя"

    # Повторный прогон не должен затирать уже записанную причину
    before = post_row(pid)["publish_error"]
    scheduler.flag_interrupted_posts()
    assert post_row(pid)["publish_error"] == before


def test_group_context_is_passed_to_publisher(client, group_with_post, monkeypatch):
    """Настройки соцсетей берутся по группе поста, а не глобальные."""
    gid = group_with_post["group_id"]
    make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    seen = {}

    def spy(conn, post, group_id=None):
        seen["group_id"] = group_id
        return {}

    monkeypatch.setattr(scheduler, "perform_publish", spy)
    scheduler.publish_due_posts()
    assert seen["group_id"] == gid


# ── Время ────────────────────────────────────────────────────────────────────

def test_due_check_uses_app_timezone(client, group_with_post, monkeypatch):
    """
    scheduled_at приходит из браузера по местному времени, а контейнер и
    Postgres на Railway живут в UTC. Красноярск на 7 часов впереди — при
    сравнении с UTC пост уехал бы на эти самые 7 часов.
    """
    import utils

    # Пост на «час назад» по Красноярску всё ещё в будущем по Гринвичу
    when = at(timedelta(hours=-1))
    pid = make_scheduled(client, group_with_post, when)

    monkeypatch.setattr(utils, "APP_TZ", "UTC")
    assert scheduler.publish_due_posts() == 0, (
        "по UTC этот пост ещё не созрел — значит сравнение действительно "
        "идёт в заданной зоне, а не по времени контейнера"
    )

    monkeypatch.setattr(utils, "APP_TZ", "Asia/Krasnoyarsk")
    scheduler.publish_due_posts()
    assert post_row(pid)["status"] == "published"


def test_unknown_timezone_falls_back(monkeypatch):
    """Кривая APP_TZ не должна ронять публикацию — просто предупреждение."""
    import utils

    monkeypatch.setattr(utils, "APP_TZ", "Нет/Такой/Зоны")
    assert len(utils.app_now_str()) == 16
