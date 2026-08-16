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
from conftest import auth, drain_publish_queue

import publish_queue
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


def last_job(pid: int) -> dict:
    """Последняя задача публикации по посту."""
    from publish_queue import job_for_post

    conn = get_db()
    try:
        return job_for_post(conn, pid) or {}
    finally:
        conn.close()


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
    drain_publish_queue()

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
    drain_publish_queue()
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

    monkeypatch.setattr(publish_queue, "perform_publish", explode)
    scheduler.publish_due_posts()
    drain_publish_queue()

    assert post_row(pid)["publish_attempts"] == 1
    job = last_job(pid)
    assert job["state"] == "failed"
    assert "ВК недоступен" in (job["error"] or "")

    monkeypatch.undo()
    assert scheduler.publish_due_posts() == 0, "повторять автоматически нельзя"
    assert drain_publish_queue() == 0


def test_failure_is_visible_on_the_job(client, group_with_post, monkeypatch):
    """
    Причина неудачи должна сохраняться: раньше она жила только в уведомлении,
    которое можно смахнуть и не найти.
    """
    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)), "Упавший")
    monkeypatch.setattr(publish_queue, "perform_publish", lambda *a, **kw: 1 / 0)
    scheduler.publish_due_posts()
    drain_publish_queue()

    job = last_job(pid)
    assert job["state"] == "failed"
    assert job["error"]


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
    drain_publish_queue()
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
    drain_publish_queue()
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

    monkeypatch.setattr(publish_queue, "perform_publish", spy)
    scheduler.publish_due_posts()
    drain_publish_queue()
    assert seen["group_id"] == gid


# ── Время ────────────────────────────────────────────────────────────────────

def test_due_check_no_longer_depends_on_a_zone_setting(client, group_with_post, monkeypatch):
    """
    Раньше срок хранился строкой без зоны, и сравнение зависело от того, в
    какой зоне считать «сейчас»: с UTC вместо Красноярска пост уезжал на семь
    часов. Теперь в базе абсолютный момент — смена APP_TZ на это не влияет.
    """
    import utils

    pid = make_scheduled(client, group_with_post, at(timedelta(minutes=-5)))
    monkeypatch.setattr(utils, "APP_TZ", "UTC")
    assert scheduler.publish_due_posts() >= 1, (
        "созревший пост обязан выйти независимо от настройки зоны"
    )
    drain_publish_queue()
    assert post_row(pid)["status"] == "published"


def test_scheduled_moment_is_absolute(client, group_with_post):
    """
    Человек назначает местное время, а хранится момент. Пост, назначенный на
    час вперёд, не должен считаться созревшим ни при какой зоне.
    """
    pid = make_scheduled(client, group_with_post, at(timedelta(hours=1)))
    assert scheduler.publish_due_posts() == 0
    assert post_row(pid)["status"] == "scheduled"


def test_unknown_timezone_falls_back(monkeypatch):
    """Кривая APP_TZ не должна ронять публикацию — просто предупреждение."""
    import utils

    monkeypatch.setattr(utils, "APP_TZ", "Нет/Такой/Зоны")
    assert len(utils.app_now_str()) == 16
