#!/usr/bin/env bash
#
# Резервная копия: база и загруженные файлы.
#
#   bash deploy/backup.sh
#
# Ставится в cron — раз в сутки ночью:
#   0 3 * * * /srv/mediahub/deploy/backup.sh >> /var/log/mediahub-backup.log 2>&1
#
# Копия у себя же на диске спасает от ошибки человека, но не от потери сервера.
# Настройте отдачу каталога на внешнее хранилище отдельно.

set -euo pipefail

# Где лежит проект. Определяем по расположению самого скрипта, а не жёстким
# путём: репозиторий клонируют куда придётся, и скрипт, ищущий файлы по
# адресу, где его нет, падает уже на середине установки — с сообщением про
# отсутствующий requirements.txt, по которому причина совершенно не видна.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-$REPO_ROOT}"
DATA_DIR="${DATA_DIR:-/var/lib/mediahub}"
BACKUP_DIR="${BACKUP_DIR:-$DATA_DIR/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

set -a
# shellcheck disable=SC1091
. "$APP_DIR/backend/.env"
set +a

STAMP="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$BACKUP_DIR"

# Схема и данные одним файлом. --clean --if-exists делает копию пригодной
# для восстановления поверх существующей базы.
pg_dump --clean --if-exists --no-owner --dbname="$DATABASE_URL" \
    | gzip > "$BACKUP_DIR/db-$STAMP.sql.gz"

# Загрузки: без них база бесполезна — все посты будут ссылаться в пустоту.
UPLOADS="${UPLOAD_DIR:-$DATA_DIR/uploads}"
if [[ -d "$UPLOADS" ]]; then
    tar -czf "$BACKUP_DIR/uploads-$STAMP.tar.gz" -C "$(dirname "$UPLOADS")" "$(basename "$UPLOADS")"
fi

find "$BACKUP_DIR" -name '*.gz' -mtime "+$KEEP_DAYS" -delete

DB_SIZE="$(du -h "$BACKUP_DIR/db-$STAMP.sql.gz" | cut -f1)"
echo "$(date '+%F %T')  копия готова: db-$STAMP.sql.gz ($DB_SIZE)"
