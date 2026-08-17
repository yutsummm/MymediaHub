"""
Логи и наблюдаемость.

Единственным способом узнать об ошибке на проде был `print` и трейсбек в
stderr: без уровней, без привязки к обращению, без возможности отличить
предупреждение от отказа. Жалобу «у меня не сохранился пост» сопоставить с
записью в логе было нечем.

Здесь стерегутся три вещи. Первая: у каждого ответа есть идентификатор
обращения, и он же уходит в лог — по нему запись находится точным поиском.
Вторая: наружу из непойманной ошибки уходит только этот идентификатор, а не
трейсбек. Третья: логи вообще работают — были они выключены целиком, и
заметить это без специальной проверки нельзя.
"""
import logging

import pytest
from conftest import auth
from fastapi.testclient import TestClient

import health
import main
from logs import JsonFormatter, get_logger, request_id_var


@pytest.fixture()
def raw_client(app):
    """
    Клиент, который не перебрасывает исключение обработчика наружу, а отдаёт
    настоящий HTTP-ответ, — только так проверяется, что видит пользователь.
    """
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module", autouse=True)
def boom_route(request):
    """Роут, который гарантированно падает. Нужен ровно этим тестам."""
    @main.app.get("/api/tests/boom")
    def boom():
        raise RuntimeError("нарочно сломано")

    yield
    main.app.router.routes = [
        r for r in main.app.router.routes if getattr(r, "path", "") != "/api/tests/boom"
    ]


# ── Идентификатор обращения ──────────────────────────────────────────────────

def test_every_response_carries_request_id(client):
    r = client.get("/")
    assert r.headers.get("X-Request-Id"), "по чему тогда искать запись в логе"


def test_incoming_request_id_is_kept(client):
    """Если идентификатор прислали, берём его: так наша запись сшивается с чужой."""
    r = client.get("/", headers={"X-Request-Id": "from-outside-123"})
    assert r.headers["X-Request-Id"] == "from-outside-123"


def test_request_id_is_unique_per_request(client):
    first = client.get("/").headers["X-Request-Id"]
    second = client.get("/").headers["X-Request-Id"]
    assert first != second


# ── Непойманная ошибка ───────────────────────────────────────────────────────

def test_unhandled_error_returns_reference_not_traceback(raw_client, caplog):
    with caplog.at_level(logging.ERROR):
        r = raw_client.get("/api/tests/boom")
    assert r.status_code == 500
    body = r.json()

    assert body["request_id"], "человеку нечего назвать в обращении"
    assert body["request_id"] in body["detail"]
    # Устройство наружу не показываем: имена модулей и путей — не дело клиента.
    dump = r.text
    for leak in ("Traceback", "RuntimeError", "нарочно сломано", "main.py"):
        assert leak not in dump, f"наружу утекло: {leak}"


def test_unhandled_error_is_logged_with_traceback(raw_client, caplog):
    with caplog.at_level(logging.ERROR):
        r = raw_client.get("/api/tests/boom")
    # То, чего нет в ответе, обязано быть в логе — иначе чинить нечем.
    assert "нарочно сломано" in caplog.text
    failures = [rec for rec in caplog.records if rec.exc_info]
    assert failures, "трейсбек не записан"
    # Запись и ответ должны сходиться по идентификатору: иначе по коду из
    # обращения найти в логе будет нечего.
    assert failures[-1].request_id == r.json()["request_id"]


# ── Запись про сам запрос ────────────────────────────────────────────────────

def test_request_is_logged_with_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger="mediahub.app"):
        client.get("/api/posts", headers={"Authorization": "Bearer nope"})
    records = [r for r in caplog.records if getattr(r, "path", "") == "/api/posts"]
    assert records, "запрос не попал в лог"
    record = records[-1]
    assert record.method == "GET"
    assert record.status == 401
    assert record.duration_ms >= 0
    assert record.request_id


def test_log_knows_who_made_the_request(client, admin_token, caplog):
    """
    Идентификатор пользователя проставляется при разборе токена. Без него
    «кто-то удалил пост» так и остаётся вопросом без ответа.
    """
    with caplog.at_level(logging.INFO, logger="mediahub.app"):
        client.get("/api/posts", headers=auth(admin_token))
    records = [r for r in caplog.records if getattr(r, "path", "") == "/api/posts"]
    assert records[-1].user_id is not None


def test_slow_request_is_a_warning(client, caplog, monkeypatch):
    """Медленный ответ — не норма, его надо видеть отдельно от остальных."""
    monkeypatch.setattr(main, "SLOW_REQUEST_MS", 0)
    with caplog.at_level(logging.INFO, logger="mediahub.app"):
        client.get("/api/posts", headers={"Authorization": "Bearer nope"})
    records = [r for r in caplog.records if getattr(r, "path", "") == "/api/posts"]
    assert records[-1].levelno == logging.WARNING


# ── Логи должны работать вообще ──────────────────────────────────────────────

def test_migrations_do_not_silence_the_app():
    """
    Регрессия: alembic настраивал логирование через fileConfig, а тот по
    умолчанию выключает все ранее созданные логгеры и переставляет уровень
    корневого. Миграции катятся из startup-хука — то есть после того, как
    модули завели свои логгеры, — и приложение после старта замолкало целиком.
    Отсутствие логов нечем заметить, кроме такой проверки.
    """
    main.run_migrations()
    for name in ("app", "auth", "scheduler", "publish", "utils"):
        logger = get_logger(name)
        assert not logger.disabled, f"логгер {logger.name} выключен миграциями"
        assert logger.isEnabledFor(logging.INFO), f"логгер {logger.name} потерял уровень"


def test_json_format_contains_context():
    """На проде логи — JSON: только так их можно искать и фильтровать."""
    import json

    token = request_id_var.set("абв123")
    try:
        record = logging.LogRecord(
            "mediahub.test", logging.INFO, "x.py", 1, "сообщение", None, None
        )
        record.request_id = request_id_var.get()
        record.status = 500
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert line["level"] == "INFO"
    assert line["message"] == "сообщение"
    assert line["request_id"] == "абв123"
    assert line["status"] == 500, "поля из extra= должны доезжать до JSON"


def test_setup_logging_keeps_foreign_handlers():
    """
    Своё настраиваем, чужое не трогаем: на корневом логгере висит перехватчик
    pytest, и снос всех обработчиков тихо ломал проверку логов во всех тестах.
    """
    from logs import setup_logging

    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        setup_logging()
        assert foreign in root.handlers
        mine = [h for h in root.handlers if getattr(h, "_mediahub", False)]
        assert len(mine) == 1, "повторная настройка не должна множить обработчики"
    finally:
        root.removeHandler(foreign)


# ── Проверка состояния ───────────────────────────────────────────────────────

def test_health_is_open_and_answers_ok(client):
    """Мониторинг ходит без токена — иначе проверять состояние нечем."""
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"]["ok"] is True
    assert body["schema"]["ok"] is True
    assert "publish_queue" in body and "loops" in body


def test_health_sections_actually_ran(client):
    """
    Ни одна проверка не должна отчитываться ошибкой на исправной системе.

    Прежние тесты смотрели только на `status`, а он остаётся «ok», даже когда
    отдельная проверка упала: её обработчик кладёт в отчёт `{"error": ...}` и
    идёт дальше. Так на проде и жил счётчик просроченных постов — запрос падал
    на `make_interval(mins => ...)` (у параметра тип integer, а деление в Python
    даёт float), сообщение молча оседало в теле ответа, а «всё в порядке»
    продолжало гореть. Между тем именно этот счётчик — единственный внешний
    признак того, что планировщик встал.
    """
    body = client.get("/api/health").json()

    broken = {
        name: section["error"]
        for name, section in body.items()
        if isinstance(section, dict) and "error" in section
    }
    assert not broken, f"проверки состояния упали, а status остался «ok»: {broken}"

    # Счётчик обязан быть числом: словарь на его месте — это отчёт об ошибке.
    assert isinstance(body["overdue_posts"], int), body["overdue_posts"]


def test_health_does_not_leak_anything_sensitive(client):
    """Ручка открыта, поэтому наружу — только флаги и счётчики."""
    dump = client.get("/api/health").text.lower()
    for leak in ("password", "token", "postgresql://", "secret", "@"):
        assert leak not in dump, f"в ответе health оказалось лишнее: {leak}"


def test_health_reports_broken_database(client, monkeypatch):
    """Отказ базы обязан быть виден как отказ, а не как «ok» с оговоркой."""
    def explode():
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(health, "get_db", explode)
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["database"]["ok"] is False


def test_dead_loop_is_visible(client, monkeypatch):
    """
    Смерть фонового цикла снаружи ничем не видна: отложенные посты просто
    перестают выходить. Пульс — единственный способ это заметить.
    """
    from datetime import timedelta

    import scheduler
    from utils import app_now

    monkeypatch.setitem(
        health.HEARTBEATS, "scheduler",
        app_now() - timedelta(seconds=scheduler.SCHEDULER_INTERVAL * 10),
    )
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["loops"]["scheduler"]["ok"] is False


def test_fresh_start_is_not_an_alarm(client):
    """
    Пульса ещё нет — цикл просто не успел отработать первый такт. Считать это
    отказом нельзя: иначе каждая выкатка поднимала бы тревогу.
    """
    health.HEARTBEATS.clear()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["loops"]["scheduler"]["last_run_seconds_ago"] is None


# ── Утечка внутренностей ─────────────────────────────────────────────────────

def test_smtp_test_is_closed_and_quiet(client, make_user):
    """
    Ручка была открыта всем и возвращала в теле полный трейсбек — это имена
    модулей, пути и адрес почтового сервера.
    """
    assert client.get("/api/debug/smtp-test").status_code == 401
    token, _ = make_user("не-админ")
    assert client.get("/api/debug/smtp-test", headers=auth(token)).status_code == 403


def test_smtp_failure_does_not_leak_traceback(client, admin_token, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "кто-то@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "пароль")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1")
    r = client.get("/api/debug/smtp-test", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "Traceback" not in r.text
