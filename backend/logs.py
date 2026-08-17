"""
Логи и наблюдаемость.

Раньше единственным способом узнать об ошибке был `print` и трейсбек в stderr.
Проблемы у этого две, и обе видны только на проде.

Первая: ошибку нельзя связать с обращением. Человек пишет «у меня не
сохранился пост», а в логе — двадцать одинаковых трейсбеков без пометки, чей
он и какой запрос его вызвал. Теперь у каждого запроса есть идентификатор:
он попадает в каждую запись лога, уходит в заголовке `X-Request-Id` и
показывается в теле пятисотки. «Ошибка 7f3a…» — и запись находится точным
поиском.

Вторая: `print` пишет в stdout без уровня, поэтому предупреждение,
ошибка и «всё хорошо» в логе Railway выглядят одинаково, и фильтровать нечего.
Теперь это `logging` с уровнями, а на проде — JSON-строки, по которым можно
искать и строить графики.

Формат выбирается сам: локально человекочитаемый, на Railway (или при
`LOG_FORMAT=json`) — JSON. Уровень — `LOG_LEVEL`, по умолчанию INFO.
"""
import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar

# Контекст текущего запроса. ContextVar, а не глобальная переменная: обработчики
# ходят в базу через asyncio.to_thread, и значение обязано ехать за задачей.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Railway свои переменные проставляет сам — по ним и понимаем, что мы на проде.
ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_NAME"))
LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if ON_RAILWAY else "human").lower()

# Поля, которые logging кладёт в запись сам. Всё, что сверх этого, добавил
# вызывающий через extra= — такие поля уезжают в JSON как есть.
_STANDARD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"asctime", "message", "taskName"}


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


class ContextFilter(logging.Filter):
    """Подмешивает в каждую запись, к какому запросу и пользователю она относится."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Только если вызывающий не указал своё. Фильтр висит на обработчике и
        # правит общую запись — затирая явно переданное значение, он молча
        # обесценивал бы `extra={"request_id": ...}` у всех остальных
        # обработчиков, включая перехватчик тестов.
        if not getattr(record, "request_id", ""):
            record.request_id = request_id_var.get()
        if getattr(record, "user_id", None) is None:
            record.user_id = user_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "")
        user_id = getattr(record, "user_id", None)
        if request_id:
            payload["request_id"] = request_id
        if user_id is not None:
            payload["user_id"] = user_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """Локальный формат: то же самое, но читаемое глазами."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s  %(message)s", "%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        rid = getattr(record, "request_id", "")
        return f"{line}  [{rid}]" if rid else line


def setup_logging() -> None:
    """
    Настраивает корневой логгер. Идемпотентно — повторный вызов не удваивает
    обработчики (важно для тестов: приложение там поднимается много раз).
    """
    root = logging.getLogger()
    # Снимаем только свой обработчик. Чужие трогать нельзя: на корневом логгере
    # висит перехватчик pytest (caplog), и удаление его здесь тихо ломало бы
    # проверку логов во всём наборе тестов.
    for handler in root.handlers[:]:
        if getattr(handler, "_mediahub", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if LOG_FORMAT == "json" else HumanFormatter())
    handler.addFilter(ContextFilter())
    # Метка «наш обработчик», см. выше.
    handler._mediahub = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)

    # uvicorn пишет своё сообщение на каждый запрос — у нас есть своё, с
    # длительностью и идентификатором. Два одинаковых на запрос ни к чему.
    logging.getLogger("uvicorn.access").disabled = True
    # alembic сюда не входит сознательно: строки «Running upgrade …» — это
    # единственный след того, что схема поехала, и на старте они нужны.
    for noisy in ("uvicorn.error", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mediahub.{name}")


# Настраиваем сразу при импорте модуля. Иначе всё, что пишется на импорте
# других модулей (а туда попадает, например, предупреждение об отсутствующем
# JWT_SECRET), уходит мимо форматтера — раньше приложения его просто не видно.
setup_logging()
