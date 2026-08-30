"""
ИИ-помощник: настраиваемая модель и честные сообщения об отказе.

Поводом стал реальный случай: Groq вывел из обращения `llama-3.1-8b-instant`,
на которой помощник работал, и кнопка перестала действовать. Ключ при этом был
исправен — сервис отвечал 200 на список моделей, — но приложение показывало
«Ошибка Groq API», и первым делом пошли проверять ключи.

Отсюда два требования, которые здесь и стерегутся:

* **модель задаётся переменной окружения** — вывод модели из обращения не
  должен требовать выкатки;
* **по сообщению видно, что чинить**: «ключ не приняли» и «модели больше нет» —
  это разные действия, и путать их нельзя.
"""
import os

import pytest
import requests as http_requests
from conftest import auth

import routers.posts as posts_router


def enhance(client, token: str, text: str = "Уведомляем о проведении мероприятия."):
    return client.post("/api/ai-enhance", headers=auth(token),
                       json={"text": text, "mode": "creative"})


class FakeResponse:
    """Ответ Groq с нужным кодом и телом ошибки."""

    def __init__(self, status: int, message: str = ""):
        self.status_code = status
        self._message = message

    def json(self):
        return {"error": {"message": self._message}}

    def raise_for_status(self):
        # requests ждёт свой Response, а обработчику нужны только код и тело
        # ошибки; поднимать настоящий объект ради этого незачем.
        error = http_requests.exceptions.HTTPError("groq failed")
        error.response = self
        raise error


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 40)


# ── Модель берётся из окружения ─────────────────────────────────────────────

def test_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    assert posts_router.groq_model() == "openai/gpt-oss-120b"


def test_model_falls_back_to_a_working_default(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    assert posts_router.groq_model() == posts_router.DEFAULT_GROQ_MODEL
    # Умолчание не должно быть моделью, которой уже нет
    assert posts_router.groq_model() != "llama-3.1-8b-instant"


def test_blank_setting_is_treated_as_unset(monkeypatch):
    """Пустая строка в переменной — обычное дело; она не должна уйти в запрос."""
    monkeypatch.setenv("GROQ_MODEL", "   ")
    assert posts_router.groq_model() == posts_router.DEFAULT_GROQ_MODEL


def test_the_configured_model_is_what_gets_requested(client, make_user, monkeypatch, with_key):
    token, _ = make_user("ai-model")
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    sent: dict = {}

    class Ok:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "готово"}}]}

    def fake_post(url, **kw):
        sent.update(kw.get("json") or {})
        return Ok()

    monkeypatch.setattr(posts_router.http_requests, "post", fake_post)
    r = enhance(client, token)
    assert r.status_code == 200, r.text
    assert sent["model"] == "qwen/qwen3.8-27b"


# ── Сообщения различают причины ─────────────────────────────────────────────

def test_revoked_key_says_so_and_where_to_get_a_new_one(client, make_user, monkeypatch, with_key):
    token, _ = make_user("ai-401")
    monkeypatch.setattr(posts_router.http_requests, "post",
                        lambda *a, **kw: FakeResponse(401, "Invalid API Key"))
    r = enhance(client, token)
    detail = r.json()["detail"]
    assert "ключ" in detail.lower()
    assert "console.groq.com" in detail
    assert "GROQ_MODEL" not in detail, "про модель здесь речи нет, это сбивает с толку"


def test_missing_model_says_the_key_may_be_fine(client, make_user, monkeypatch, with_key):
    """
    Ровно тот случай, ради которого всё затевалось: модель вывели, а человек
    идёт менять исправный ключ.
    """
    token, _ = make_user("ai-404")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setattr(
        posts_router.http_requests, "post",
        lambda *a, **kw: FakeResponse(404, "The model does not exist"))
    r = enhance(client, token)
    detail = r.json()["detail"]
    assert "llama-3.1-8b-instant" in detail, "не сказано, какая именно модель недоступна"
    assert "GROQ_MODEL" in detail, "не сказано, где её поменять"
    assert "исправен" in detail, "не сказано, что ключ менять не нужно"


def test_rate_limit_is_not_a_configuration_problem(client, make_user, monkeypatch, with_key):
    """
    Лимит — это «подождите», а не «что-то настроено не так». И код ответа
    должен быть 429, чтобы это отличалось снаружи.
    """
    token, _ = make_user("ai-429")
    monkeypatch.setattr(posts_router.http_requests, "post",
                        lambda *a, **kw: FakeResponse(429, "Rate limit reached"))
    r = enhance(client, token)
    assert r.status_code == 429
    assert "лимит" in r.json()["detail"].lower()


def test_unknown_failure_still_reports_what_the_service_said(client, make_user,
                                                             monkeypatch, with_key):
    token, _ = make_user("ai-500")
    monkeypatch.setattr(posts_router.http_requests, "post",
                        lambda *a, **kw: FakeResponse(500, "Internal server error"))
    r = enhance(client, token)
    assert r.status_code == 502
    assert "Internal server error" in r.json()["detail"]


def test_missing_key_is_still_reported_separately(client, make_user, monkeypatch):
    token, _ = make_user("ai-nokey")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = enhance(client, token)
    assert r.status_code == 503
    assert "GROQ_API_KEY" in r.json()["detail"]


def test_startup_check_does_not_reach_out_to_groq(monkeypatch):
    """
    Строка в логе про модель не должна ходить в сеть: запрос к стороннему
    сервису на старте означает, что его недоступность мешает приложению
    подняться.
    """
    import main

    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 40)

    def forbidden(*a, **kw):
        raise AssertionError("стартовая проверка полезла в сеть")

    monkeypatch.setattr(posts_router.http_requests, "post", forbidden)
    monkeypatch.setattr(posts_router.http_requests, "get", forbidden, raising=False)
    main.check_ai_model()


def test_startup_check_survives_a_missing_key(monkeypatch):
    import main

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    main.check_ai_model()  # молча и без исключений
    assert os.getenv("GROQ_API_KEY") is None
