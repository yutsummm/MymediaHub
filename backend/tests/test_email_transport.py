"""
Отправка писем: путь выбирается настройками, а отказ называет причину.

Письма остались только для сброса пароля, но требования к отправке прежние:

* **поставщик — сменная деталь**: SMTP говорят все почтовые службы, и переход
  не должен стоить выкатки;
* **отправитель совпадает с ящиком, под которым вошли** — иначе Яндекс и
  соседи отвергают письмо целиком;
* **у письма есть текстовая часть** — письмо из одного HTML фильтры охотнее
  считают рассылкой;
* **по сообщению об отказе видно, что чинить**: пароль, отправитель или
  недоступный сервер — это три разных действия;
* **`.env.example` не обещает того, чего нет.** Он уже однажды описывал выбор
  между Brevo и SMTP, которого в коде не было.
"""
import os
import pathlib
import smtplib

import pytest

import utils

# conftest глобально затыкает отправку писем, чтобы ни один тест не отправил
# письмо по-настоящему, — предохранитель правильный. Но здесь проверяется сама
# отправка, поэтому берём настоящие функции до подмены. Наружу всё равно ничего
# не уйдёт: почтовый сервер в этих тестах подставной.
send_reset = utils.send_reset_email


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("EMAIL_TRANSPORT", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
                 "SMTP_PASSWORD", "BREVO_API_KEY", "BREVO_SENDER_EMAIL",
                 "BREVO_SENDER_NAME", "MAIL_SENDER_NAME"):
        monkeypatch.delenv(name, raising=False)


class FakeSMTP:
    """Подставной сервер: запоминает, что ему передали."""
    last: dict = {}

    def __init__(self, host, port, timeout=None):
        FakeSMTP.last = {"host": host, "port": port, "timeout": timeout,
                         "starttls": False, "login": None, "message": None,
                         "ssl": type(self).__name__ == "FakeSMTPSSL"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        FakeSMTP.last["starttls"] = True

    def login(self, user, password):
        FakeSMTP.last["login"] = (user, password)

    def send_message(self, msg):
        FakeSMTP.last["message"] = msg


class FakeSMTPSSL(FakeSMTP):
    pass


def use_smtp(monkeypatch, port="587"):
    monkeypatch.setenv("SMTP_HOST", "smtp.yandex.ru")
    monkeypatch.setenv("SMTP_PORT", port)
    monkeypatch.setenv("SMTP_USER", "mediahub@yandex.ru")
    monkeypatch.setenv("SMTP_PASSWORD", "пароль-приложения")


# ── Выбор пути ──────────────────────────────────────────────────────────────

def test_smtp_wins_when_configured(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-что-то")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "a@b.ru")
    assert utils.email_transport() == "smtp"


def test_brevo_when_no_smtp(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-что-то")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "a@b.ru")
    assert utils.email_transport() == "brevo"


def test_explicit_choice_beats_guessing(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-что-то")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "a@b.ru")
    monkeypatch.setenv("EMAIL_TRANSPORT", "brevo")
    assert utils.email_transport() == "brevo"


def test_nothing_configured_says_so(monkeypatch):
    assert utils.email_transport() == "none"
    with pytest.raises(ValueError) as e:
        send_reset("kto@to.ru", "123456")
    assert "не настроена" in str(e.value)


# ── Само письмо ─────────────────────────────────────────────────────────────

def test_sender_matches_the_mailbox_we_logged_in_with(monkeypatch):
    """
    Отправитель обязан совпадать с ящиком входа: чужой адрес в поле «От кого»
    почтовые службы отвергают, и письмо не уходит вовсе.
    """
    use_smtp(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    send_reset("volonter@mail.ru", "123456")
    msg = FakeSMTP.last["message"]
    assert "mediahub@yandex.ru" in msg["From"]
    assert FakeSMTP.last["login"] == ("mediahub@yandex.ru", "пароль-приложения")


def test_letter_carries_plain_text_beside_html(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    send_reset("volonter@mail.ru", "654321")
    msg = FakeSMTP.last["message"]
    kinds = {part.get_content_type() for part in msg.walk()}
    assert "text/plain" in kinds and "text/html" in kinds
    # Код виден в обеих частях: иначе человек с простым почтовиком его не найдёт
    assert "654321" in msg.get_body(("plain",)).get_content()
    assert "654321" in msg.get_body(("html",)).get_content()


def test_port_465_goes_straight_to_secure_channel(monkeypatch):
    use_smtp(monkeypatch, port="465")
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    send_reset("kto@to.ru", "111222")
    assert FakeSMTP.last["ssl"] is True
    assert FakeSMTP.last["starttls"] is False


def test_port_587_upgrades_the_channel(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    send_reset("kto@to.ru", "111222")
    assert FakeSMTP.last["starttls"] is True


# ── Отказы называют причину ─────────────────────────────────────────────────

def raising(exc):
    class Raiser(FakeSMTP):
        def login(self, user, password):
            raise exc
    return Raiser


def test_bad_password_points_at_the_app_password(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP",
                        raising(smtplib.SMTPAuthenticationError(535, b"bad login")))
    with pytest.raises(RuntimeError) as e:
        send_reset("kto@to.ru", "123456")
    text = str(e.value)
    assert "пароль приложения" in text
    assert "SMTP" in text


def test_wrong_sender_is_named_as_such(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP",
                        raising(smtplib.SMTPSenderRefused(553, b"not owned", "x@y.ru")))
    with pytest.raises(RuntimeError) as e:
        send_reset("kto@to.ru", "123456")
    assert "отправителя" in str(e.value)


def test_unreachable_server_is_not_confused_with_bad_password(monkeypatch):
    use_smtp(monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP", raising(TimeoutError("timed out")))
    with pytest.raises(RuntimeError) as e:
        send_reset("kto@to.ru", "123456")
    text = str(e.value)
    assert "связаться" in text
    assert "пароль" not in text


def test_brevo_refusals_are_distinguishable(monkeypatch):
    """Каждая из двух реальных поломок Brevo должна называться своим именем."""
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-что-то")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "a@b.ru")

    class Resp:
        def __init__(self, code, text):
            self.status_code, self.text = code, text

    cases = [
        (401, '{"message":"unrecognised IP address 1.2.3.4"}', "ограничение по IP"),
        (403, '{"message":"SMTP account is not yet activated"}', "транзакционную отправку"),
        (402, '{"message":"no credits"}', "лимит"),
    ]
    for code, body, expected in cases:
        monkeypatch.setattr(utils.http_requests, "post",
                            lambda *a, _r=Resp(code, body), **k: _r)
        with pytest.raises(RuntimeError) as e:
            send_reset("kto@to.ru", "123456")
        assert expected in str(e.value), f"{code} должен называться причиной"


# ── Описание не расходится с кодом ──────────────────────────────────────────

def test_env_example_documents_every_variable_the_code_reads():
    """
    `.env.example` уже однажды обещал выбор между Brevo и SMTP, которого в коде
    не существовало: `smtplib` жил в отладочной ручке и писем не отправлял.
    Человек заполнял SMTP-переменные и ждал, что почта заработает.
    """
    example = (pathlib.Path(__file__).resolve().parents[1] / ".env.example").read_text()
    for name in ("EMAIL_TRANSPORT", "SMTP_HOST", "SMTP_PORT", "SMTP_USER",
                 "SMTP_PASSWORD", "MAIL_SENDER_NAME"):
        assert name in example, f"{name} читается кодом, но не описан в .env.example"
