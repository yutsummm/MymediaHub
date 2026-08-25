"""
Начало работы: шаги, которые ещё не сделаны в этой группе.

У системы больше тридцати функций и ни одной подсказки о том, что они есть.
Человек, зашедший впервые, видит пустой дашборд и не знает ни про
согласование, ни про медиатеку, ни про расписание, ни про отчёты. Половина
уже написанной работы просто не найдена.

**Состояние шагов вычисляется по данным, а не хранится флагами.** Флаг
«подключил ВК» умеет разойтись с реальностью: интеграцию отключили, а галочка
осталась. Вычисляемый шаг сам погаснет и сам загорится обратно — и заодно не
требует ни миграции, ни отдельного места, где эта правда живёт.

Порядок неслучаен: сначала то, без чего система не работает вообще
(интеграции), потом то, что делает её командной, потом удобства.
"""


def _one(key: str, title: str, hint: str, done: bool, href: str,
         optional: bool = False) -> dict:
    return {"key": key, "title": title, "hint": hint, "done": done,
            "href": href, "optional": optional}


def steps(conn, gid: int, role: str) -> list[dict]:
    c = conn.cursor()

    def scalar(sql: str, params=()) -> int:
        c.execute(sql, params)
        row = c.fetchone()
        return (list(row.values())[0] if row else 0) or 0

    networks = scalar(
        "SELECT (SELECT COUNT(*) FROM vk_settings WHERE workspace_id=%s) "
        "     + (SELECT COUNT(*) FROM tg_settings WHERE workspace_id=%s) AS n",
        (gid, gid),
    )
    posts = scalar("SELECT COUNT(*) AS n FROM posts WHERE group_id=%s", (gid,))
    published = scalar(
        "SELECT COUNT(*) AS n FROM posts WHERE group_id=%s AND status='published'", (gid,))
    members = scalar("SELECT COUNT(*) AS n FROM group_members WHERE group_id=%s", (gid,))
    slots = scalar("SELECT COUNT(*) AS n FROM publishing_slots WHERE group_id=%s", (gid,))

    c.execute("SELECT require_approval, variables, utm_enabled FROM groups WHERE id=%s", (gid,))
    group = c.fetchone() or {}
    variables = group.get("variables") if isinstance(group.get("variables"), dict) else {}

    result = [
        _one("network", "Подключить ВКонтакте или Telegram",
             "Без подключённой площадки публиковать некуда — это первый шаг",
             networks > 0, "/settings"),
        _one("post", "Создать первый пост",
             "Шаблон подскажет структуру, а ИИ-помощник поможет с текстом",
             posts > 0, "/posts/new"),
        _one("publish", "Опубликовать пост",
             "После публикации появится статистика и обращения от жителей",
             published > 0, "/posts"),
        _one("team", "Пригласить команду",
             "Ссылка-приглашение сразу вводит человека в группу с нужной ролью",
             members > 1, "/settings"),
        _one("approval", "Настроить порядок публикации",
             "Редактор готовит пост, а выпускаете вы — если такой порядок нужен",
             bool(group.get("require_approval")), "/settings", optional=True),
        _one("slots", "Задать расписание",
             "Указали свои дни и время — дальше пост встаёт в очередь одной кнопкой",
             slots > 0, "/settings", optional=True),
        _one("variables", "Добавить подстановки",
             "Адрес и телефон центра — одним нажатием вместо набора заново",
             bool(variables), "/settings", optional=True),
        _one("utm", "Включить метки для статистики сайта",
             "Иначе переходы из соцсетей видны как «прямые заходы»",
             bool(group.get("utm_enabled")), "/settings", optional=True),
    ]

    # Шаги, ведущие в настройки группы, показываем только тем, кто может их
    # менять: подсказка «сделайте то, что вам запрещено» — это издевательство.
    if role != "admin":
        result = [s for s in result if s["href"] != "/settings"]
    return result


def progress(conn, gid: int, role: str) -> dict:
    items = steps(conn, gid, role)
    required = [s for s in items if not s["optional"]]
    return {
        "steps": items,
        "done": sum(1 for s in required if s["done"]),
        "total": len(required),
        # Основное пройдено — карточку начала работы пора убирать с глаз:
        # подсказка, которая не подсказывает, превращается в шум.
        "complete": all(s["done"] for s in required),
    }
