#!/usr/bin/env bash
#
# Обновление медиаПространства до свежей версии.
#
#   bash deploy/update.sh          # обновиться из git и перезапустить
#   bash deploy/update.sh --local  # то же, но без git pull (код уже на месте)
#
# Порядок здесь важен и выбран не случайно:
#   код → зависимости → СБОРКА фронта → миграции → перезапуск
# Сборка идёт до миграций и до остановки сервисов: если она упадёт, ничего
# ещё не тронуто и старая версия продолжает работать.

set -euo pipefail

# Где лежит проект. Определяем по расположению самого скрипта, а не жёстким
# путём: репозиторий клонируют куда придётся, и скрипт, ищущий файлы по
# адресу, где его нет, падает уже на середине установки — с сообщением про
# отсутствующий requirements.txt, по которому причина совершенно не видна.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-$REPO_ROOT}"
APP_USER="${APP_USER:-mediahub}"
PULL=1
[[ "${1:-}" == "--local" ]] && PULL=0

say()  { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Запускайте от root: sudo bash deploy/update.sh"
[[ -f "$APP_DIR/backend/.env" ]] || fail "Нет $APP_DIR/backend/.env — заполните его по образцу .env.example"
[[ -f "$APP_DIR/frontend/.env" ]] || fail "Нет $APP_DIR/frontend/.env — заполните его по образцу .env.example"

cd "$APP_DIR"

if [[ $PULL -eq 1 ]]; then
    say "Забираем свежий код"
    sudo -u "$APP_USER" git pull --ff-only
    echo "  $(git log --oneline -1)"
fi

say "Обновляем зависимости"
"$APP_DIR/venv/bin/pip" install -q -r backend/requirements.txt
(cd frontend && sudo -u "$APP_USER" npm ci --silent --no-audit --no-fund)

say "Собираем интерфейс"
# Собираем ДО остановки сервисов: упавшая сборка не должна оставлять сайт лежащим.
(cd frontend && set -a && . ./.env && set +a && sudo -u "$APP_USER" -E npm run build) \
    || fail "Сборка интерфейса не прошла. Ничего не изменено, старая версия работает."

say "Применяем схему базы"
# Отдельной командой, до запуска нового кода: приложение отказывается
# подниматься на отставшей схеме, и это правильно — обслуживать запросы на
# неполной схеме значит выдавать людям пятисотки вместо честного отказа.
(cd backend && set -a && . ./.env && set +a && sudo -u "$APP_USER" -E "$APP_DIR/venv/bin/python" manage.py migrate) \
    || fail "Миграции не применились. Сервисы не перезапускались."

say "Перезапускаем сервисы"
systemctl restart mediahub-backend
systemctl restart mediahub-frontend

say "Проверяем, что поднялось"
for i in $(seq 1 30); do
    sleep 2
    if curl -fsS --max-time 5 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        STATUS="$(curl -fsS http://127.0.0.1:8000/api/health \
            | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], "|", d["schema"]["message"])')"
        echo "  бэкенд: $STATUS"
        break
    fi
    [[ $i -eq 30 ]] && fail "Бэкенд не ответил за минуту. Смотрите: journalctl -u mediahub-backend -n 50"
done

curl -fsS --max-time 10 -o /dev/null http://127.0.0.1:3000/login \
    && echo "  интерфейс: отвечает" \
    || fail "Интерфейс не отвечает. Смотрите: journalctl -u mediahub-frontend -n 50"

say "Готово"
