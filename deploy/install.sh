#!/usr/bin/env bash
#
# Первичная установка медиаПространства на Ubuntu.
#
# Скрипт делает механическую часть: пакеты, пользователя, каталоги, базу,
# зависимости. Он НЕ заполняет .env и не выпускает сертификат — это решения,
# а не операции, и делать их молча за человека неправильно.
#
# Запускать от root:  bash deploy/install.sh
#
# Повторный запуск безопасен: всё, что уже сделано, пропускается.

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/mediahub}"
DATA_DIR="${DATA_DIR:-/var/lib/mediahub}"
APP_USER="${APP_USER:-mediahub}"
DB_NAME="${DB_NAME:-mediahub}"
DB_USER="${DB_USER:-mediahub}"

say()  { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m⚠  %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "Запускайте от root: sudo bash deploy/install.sh" >&2; exit 1; }

say "Устанавливаем пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-dev \
    postgresql postgresql-contrib \
    nginx curl git ca-certificates gnupg

# Node.js 20: в репозитории Ubuntu лежит слишком старая версия для Next 14.
if ! command -v node >/dev/null || [[ "$(node -v)" != v20.* && "$(node -v)" != v22.* ]]; then
    say "Ставим Node.js 20"
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list
    apt-get update -qq
    apt-get install -y -qq nodejs
fi
echo "  node $(node -v), python $(python3 -V | cut -d' ' -f2)"

say "Заводим пользователя $APP_USER"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    # Системный пользователь без права входа: сервису оболочка не нужна.
    adduser --system --group --home "$APP_DIR" --no-create-home "$APP_USER"
    echo "  создан"
else
    echo "  уже есть"
fi

say "Готовим каталоги"
mkdir -p "$APP_DIR" "$DATA_DIR/uploads" "$DATA_DIR/backups"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
# Загрузки — единственное, что приложению нужно писать.
chmod 750 "$DATA_DIR/uploads" "$DATA_DIR/backups"
echo "  код: $APP_DIR, данные: $DATA_DIR"

say "Готовим базу данных"
systemctl enable --now postgresql >/dev/null 2>&1 || true
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    echo "  роль $DB_USER уже есть, пароль не трогаем"
    DB_PASSWORD=""
else
    DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    sudo -u postgres psql -qc "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD'"
    echo "  роль $DB_USER создана"
fi
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    echo "  база $DB_NAME уже есть"
else
    sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
    echo "  база $DB_NAME создана"
fi

say "Ставим зависимости бэкенда"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"
echo "  готово"

say "Ставим зависимости фронтенда"
cd "$APP_DIR/frontend" && npm ci --silent --no-audit --no-fund
echo "  готово"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

say "Что осталось сделать руками"
cat <<NEXT
  1. Заполните backend/.env  (образец: backend/.env.example)
     Сгенерированные значения:
       JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
       TOKEN_ENCRYPTION_KEY=$(python3 -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')
NEXT
if [[ -n "$DB_PASSWORD" ]]; then
cat <<NEXT
       DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
NEXT
else
    warn "     Пароль базы не переустанавливался — возьмите прежний."
fi
cat <<'NEXT'
  2. Заполните frontend/.env (образец: frontend/.env.example)
  3. Установите юниты и конфиг веб-сервера:
       cp deploy/mediahub-*.service /etc/systemd/system/
       cp deploy/nginx-mediahub.conf /etc/nginx/sites-available/mediahub
       # замените в нём домен, затем
       ln -s /etc/nginx/sites-available/mediahub /etc/nginx/sites-enabled/
       nginx -t && systemctl reload nginx
  4. Выпустите сертификат:
       apt-get install -y certbot python3-certbot-nginx
       certbot --nginx -d ВАШ.ДОМЕН
  5. Примените схему и запустите:
       bash deploy/update.sh

Подробности и разбор ошибок — в DEPLOY.md
NEXT
