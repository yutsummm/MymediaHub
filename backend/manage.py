#!/usr/bin/env python
"""
Служебные команды, которые нельзя выполнять в startup-хуке приложения.

Миграции жили в хуке старта: при масштабировании больше чем в один инстанс два
процесса полезли бы накатывать их одновременно, а на Railway новый контейнер
поднимается ещё до того, как старый снят. Теперь схему двигает отдельная
release-команда (`preDeployCommand` в railway.toml), которая выполняется один
раз за выкатку и до того, как новый код начнёт обслуживать людей.

    python manage.py migrate   # применить миграции и залить сиды
    python manage.py check     # убедиться, что схема на head (ничего не меняет)

Приложение при старте только проверяет, что схема доехала, и отказывается
работать на отставшей — молча обслуживать запросы на неполной схеме хуже,
чем не подняться.
"""
import sys

import main


def cmd_migrate() -> int:
    main.run_migrations()
    main.seed_db()
    print("✅  схема и сиды применены")
    return 0


def cmd_check() -> int:
    ok, message = main.schema_is_current()
    print(("✅  " if ok else "❌  ") + message)
    return 0 if ok else 1


COMMANDS = {"migrate": cmd_migrate, "check": cmd_check}


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    handler = COMMANDS.get(name)
    if not handler:
        print(f"Использование: python manage.py [{' | '.join(COMMANDS)}]", file=sys.stderr)
        sys.exit(2)
    sys.exit(handler())
