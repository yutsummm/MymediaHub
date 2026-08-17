#!/bin/bash
# Все проверки проекта: линтеры, типы, тесты.
#   ./check.sh          — всё
#   ./check.sh backend  — только бэкенд
#   ./check.sh frontend — только фронтенд
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-all}"
PY="${PYTHON:-python3}"
[ -x "$ROOT/backend/.venv/bin/python" ] && PY="$ROOT/backend/.venv/bin/python"

if [ "$TARGET" = "all" ] || [ "$TARGET" = "backend" ]; then
  echo "🐍 Бэкенд: ruff"
  (cd "$ROOT/backend" && "$PY" -m ruff check .)

  echo "🔎 Бэкенд: mypy"
  # Ловит ровно тот класс ошибок, на котором мы уже спотыкались: перепутанные
  # типы аргументов и обращение к fetchone(), который вернул None.
  (cd "$ROOT/backend" && "$PY" -m mypy .)

  echo "🧪 Бэкенд: pytest"
  # Тестам нужен живой PostgreSQL. По умолчанию — база из docker-compose;
  # переопределяется через TEST_DATABASE_URL.
  (cd "$ROOT/backend" && "$PY" -m pytest)
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "frontend" ]; then
  echo "🔷 Фронтенд: tsc + eslint"
  (cd "$ROOT/frontend" && npm run check)
fi

echo ""
echo "✅ Все проверки пройдены"
