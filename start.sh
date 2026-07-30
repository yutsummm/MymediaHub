#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🐘 Запуск PostgreSQL (Docker)..."
docker compose -f "$ROOT/docker-compose.yml" up -d postgres

echo "⏳ Ожидание PostgreSQL..."
until docker compose -f "$ROOT/docker-compose.yml" exec postgres pg_isready -U mediahub -q; do sleep 1; done

echo "📦 Установка зависимостей бэкенда..."
pip3 install -r "$ROOT/backend/requirements.txt" -q

echo "📦 Установка зависимостей фронтенда..."
cd "$ROOT/frontend" && npm install --silent

echo ""
echo "🚀 Запуск серверов..."

# Backend
cd "$ROOT/backend" && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACK_PID=$!

# Frontend
cd "$ROOT/frontend" && npm run dev &
FRONT_PID=$!

echo ""
echo "✅ MediaHub запущен!"
echo "   Backend  → http://localhost:8000"
echo "   Frontend → http://localhost:3000"
echo ""
echo "Ctrl+C для остановки"

trap "kill $BACK_PID $FRONT_PID 2>/dev/null; docker compose -f '$ROOT/docker-compose.yml' stop" INT
wait
