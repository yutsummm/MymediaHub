# MediaHub

Медиахаб для молодёжных центров (Красноярск): планирование, генерация и публикация
контента в VK и Telegram, аналитика, приём медиа от волонтёров, карта молодёжных центров.

Интерфейс и весь текст — на русском. Пиши сообщения об ошибках и UI-строки по-русски.

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python, FastAPI 0.111, uvicorn, psycopg2 (raw SQL, **без ORM**), pydantic |
| БД | PostgreSQL 16 (локально через docker-compose), alembic для миграций |
| Auth | JWT (python-jose, HS256, 72 ч), bcrypt для паролей |
| Frontend | Next.js 14 App Router, React 18, TypeScript, **CSS без фреймворка** (globals.css) |
| Графики / карты | chart.js + react-chartjs-2, @pbe/react-yandex-maps |
| Внешние сервисы | VK API (5.199), Telegram Bot API, Groq (`llama-3.1-8b-instant`), Brevo/SMTP |
| Деплой | Railway (nixpacks), два сервиса: backend + frontend |

## Структура

```
backend/                 FastAPI, ~3.2k строк
  main.py                app, CORS, подключение роутеров, run_migrations() + seed_db()
  utils.py               get_db, JWT, bcrypt, rate limit, email, VK/TG хелперы, AI-промпты
  models.py              pydantic-схемы запросов
  routers/
    auth.py              login / register (+ email-код) / forgot / reset password
    posts.py             посты, публикация в VK+TG, sync-vk-stats, календарь, шаблоны, AI
    groups.py            группы, участники, роли, инвайт-ссылки
    settings.py          VK и Telegram интеграции (глобальные + групповые)
    analytics.py         сводка, таймлайн, экспорт в xlsx (openpyxl)
    volunteer_media.py   загрузки волонтёров и их модерация
    users.py, notifications.py, upload.py, yc.py (молодёжные центры)
  alembic/versions/      3ee67a8c2e29_initial_schema.py
frontend/
  app/(app)/             защищённые страницы: dashboard, posts, calendar,
                         analytics, notifications, settings, volunteer-media, youth-centers
  app/login|register|forgot-password|invite/[token]|groups/new
  app/config/maps/       route handlers-прокси для Яндекс.Карт (ключ + геокодер)
  components/            Sidebar, PostEditor, YouthCentersMap (526 стр.), GlobalSearch,
                         QuickPostModal, CreateGroupModal, EventLocationPickerModal, ...
  contexts/              AuthContext (user+token), GroupContext (текущая группа + кэш в
                         localStorage), ToastContext
  lib/api.ts             весь HTTP-клиент, объект `api`, типизированный обёрткой req<T>
  lib/types.ts           общие типы (Post, Group, GroupMember, AnalyticsSummary, ...)
```

## Ключевые модели данных

`users`, `groups`, `group_members` (роли: `admin` | `editor` | `volunteer`), `invite_links`,
`posts` (status: `draft` | `scheduled` | `published`; platforms/tags/media — JSON-строки),
`templates` (4 сида: announcement, results, vacancy, grant), `notifications`,
`vk_settings` / `tg_settings` (с `workspace_id` → groups), `volunteer_media`,
`email_verifications` (заявки на регистрацию до подтверждения почты), `password_resets`.

Даты в `posts`/`users` хранятся как **TEXT** в формате `YYYY-MM-DDTHH:MM`, не как timestamp.

## Архитектурные особенности (важно помнить)

- **Два параллельных набора эндпоинтов**: глобальные (`/api/posts`, `/api/settings/vk`)
  и групповые (`/api/groups/{gid}/posts`, `/api/groups/{gid}/settings/vk`). Фронт работает
  через групповые. Глобальные — легаси с одиночного воркспейса.
- **Регистрация в два шага.** `POST auth/register` пользователя не создаёт: кладёт
  заявку в `email_verifications` (имя, хеш пароля, код, `invite_token`) и шлёт код
  на почту. Аккаунт появляется только в `POST auth/verify-email`, там же
  применяется приглашение. `auth/resend-code` шлёт код заново. Ссылка-приглашение
  проверяется дважды: на первом шаге `check_invite_usable` (без расхода), на
  втором `redeem_invite` — если за это время ссылку исчерпали, аккаунт всё равно
  создаётся, а в ответе приходит `invite_error`.
- **Секреты в базе зашифрованы.** `vk_settings.access_token` и `tg_settings.bot_token`
  пишутся через `encrypt_secret()` (Fernet, префикс `enc:v1:`), читаются через
  `decrypt_secret()` / `decrypt_row_secret(row, поле)`. Ключ — `TOKEN_ENCRYPTION_KEY`,
  а если он не задан, выводится из `JWT_SECRET` через HKDF: требовать новую
  переменную нельзя, иначе на уже поднятых окружениях шифрование не включится.
  **Смена `JWT_SECRET` без переноса ключа сделает токены нечитаемыми** — интеграции
  придётся переподключить. Значения без префикса читаются как есть (легаси), а
  `encrypt_existing_secrets()` в startup дошифровывает их, идемпотентно.
- **Загрузки отдаются только по подписанной ссылке.** `/uploads/{файл}` требует
  `?exp=<unixtime>&sig=<hmac>`; без подписи — 403, с истёкшей — 410. Подпись
  считается по имени файла и сроку (ключ выводится из `JWT_SECRET`, TTL в
  `UPLOAD_URL_TTL`, по умолчанию 12 ч). Заголовок Authorization к `<img src>` не
  приложить, поэтому право доступа несёт сама ссылка: её выдаёт API тому, кто уже
  видит содержащую запись. Наружу подписывают `row_to_dict` (все посты),
  `volunteer_media` и `POST /api/upload`; **в базу медиа обязано попадать только
  через `media_for_storage()`**, который подпись срезает — иначе в базе осядет
  протухшая ссылка. Имя файла из URL берётся через `upload_filename()`, а не
  `os.path.basename` (тот утащит и query).
- **Публикация — одна функция на всех.** `publishing.perform_publish(conn, post, group_id)`;
  `group_id=None` — легаси-настройки одиночного воркспейса (строка с `id=1`).
  Её зовут обе ручки публикации и планировщик; копий больше нет.
- **Планировщик отложенных постов** — `scheduler.py`, фоновая asyncio-задача внутри
  приложения (отдельный воркер избыточен: том Railway и так держит один инстанс).
  Раз в `SCHEDULER_INTERVAL_SECONDS` (60) забирает созревшие посты.
  Заявка на публикацию — `posts.publish_attempts`: берутся только посты с нулём
  попыток, счётчик растёт тем же запросом. Блокировки строки мало: она снимается
  на коммите, а статус до публикации остаётся `scheduled`. **Повторов нет
  сознательно** — публикация не идемпотентна, повтор после таймаута даст вторую
  запись на стене. Оборвавшиеся посты подсвечивает `flag_interrupted_posts()`.
  Просроченные больше чем на `SCHEDULER_MAX_DELAY_MINUTES` (120) не публикуются
  вовсе — `flag_missed_posts()` пишет причину в `posts.publish_error`.
  Выключается через `SCHEDULER_ENABLED=0`.
- **Время приложения — `APP_TZ`** (по умолчанию `Asia/Krasnoyarsk`), `utils.app_now_str()`.
  `scheduled_at` приходит из браузера по местному времени, а контейнер и Postgres на
  Railway живут в UTC: сравнение напрямую увело бы публикацию на 7 часов.
  `published_at` теперь тоже пишется в `APP_TZ`. **`created_at` остался UTC**
  (server_default в базе) — даты в базе живут в двух разных зонах, это не доделано.
- **Авторизация**: все `/api/*` требуют `Depends(get_current_user_id)`, кроме
  `auth/login`, `auth/register`, `auth/verify-email`, `auth/resend-code`,
  `auth/forgot-password`, `auth/reset-password`,
  `GET /api/invites/{token}`, `GET /api/debug/smtp-test`. Групповые роуты проверяют
  членство через `require_group_member`. Глобальные списки постов/аналитики
  фильтруются хелпером `posts_scope` (посты групп пользователя + его посты без группы),
  одиночные операции — через `require_post_access`. Ручки вне контекста группы
  (`/api/users`, глобальные `settings/*`, `posts/sync-vk-stats`) закрыты `require_admin`
  (глобальная роль `users.role == 'admin'`).
- **Деплой.** Два сервиса Railway, nixpacks. Бэкенд катить первым (фронт шлёт токен
  на `/api/upload`). URL базы передаётся в alembic через `config.attributes`, а не через
  `alembic.ini` — ConfigParser интерполирует «%», а Railway отдаёт URL-encoded пароль.
  Конфиги `pytest`/`ruff` лежат в `pytest.ini` и `ruff.toml`, а **не** в `pyproject.toml`:
  его наличие меняет детект сборки в nixpacks.
- **Схема БД — только alembic.** При старте `run_migrations()` в [main.py](backend/main.py#L69)
  делает `alembic upgrade head`, затем `seed_db()` заливает демо-данные (идемпотентно,
  по `COUNT(*) == 0`). CREATE TABLE в коде приложения быть не должно — новая колонка
  заводится через `alembic revision`. Автогенерация недоступна (ORM нет, `target_metadata=None`),
  миграции пишутся руками через `op.*`.
  База, созданная старым `init_db()` до перехода, распознаётся по отсутствию
  `alembic_version` и помечается `BASELINE_REVISION` без повторного DDL.
- Прокси API: фронт ходит на относительные `/api/*`, next.config.mjs делает rewrite на
  `BACKEND_URL` (прод-фолбэк: `backend-production-30d6.up.railway.app`).
- Rate limit — in-memory dict в `utils.py`, сбрасывается при рестарте и не работает
  на нескольких инстансах.
- Загрузки лежат в каталоге `UPLOAD_DIR` (по умолчанию `backend/uploads/`). На Railway
  к сервису Backend примонтирован том в `/data`, а `UPLOAD_DIR=/data/uploads` — без
  этого диск контейнера пересоздаётся при выкатке и все файлы пропадают.
  `check_upload_storage()` при старте проверяет запись и пишет в лог, где реально
  лежат загрузки; если путь дефолтный, ругается предупреждением.

## Запуск

```bash
./start.sh          # postgres в docker + uvicorn :8000 + next dev :3000
```

Демо-логины (создаются сидами): `admin@mediahub.ru` / `admin123!`,
`editor@mediahub.ru` / `editor123!`, `volunteer@mediahub.ru` / `volunteer123!`.

Env: `backend/.env` (DATABASE_URL, JWT_SECRET, GROQ_API_KEY, BREVO_*/SMTP_*, ALLOWED_ORIGINS,
BACKEND_URL), `frontend/.env.local` (NEXT_PUBLIC_YANDEX_MAPS_KEY, опц. NEXT_PUBLIC_API_URL).

## Проверки

```bash
./check.sh              # всё: ruff + pytest + tsc + eslint
./check.sh backend      # только бэкенд
./check.sh frontend     # только фронтенд
```

- **Бэкенд**: `ruff` (конфиг в [backend/pyproject.toml](backend/pyproject.toml)) и `pytest`.
  Dev-зависимости — `pip install -r backend/requirements-dev.txt`.
  Тесты идут против **настоящего PostgreSQL** (база `mediahub_test` пересоздаётся каждый
  запуск, адрес переопределяется через `TEST_DATABASE_URL`) — SQL в роутерах проверяется
  по-честному. Без запущенной базы тесты не падают, а скипаются с подсказкой.
- **Фронтенд**: `npm run check` = `tsc --noEmit` + `next lint`.

Тесты, которые ловят регрессии по прошлым проблемам:
`test_auth_required.py` перебирает все роуты приложения и требует `Depends(get_current_user_id)`
у каждого, кроме явного списка публичных — новый незакрытый роут уронит сборку.
`test_migrations.py::test_app_code_contains_no_ddl` запрещает CREATE/ALTER TABLE вне alembic.
`test_registration_isolation.py` стережёт, что новичок не попадает в чужую группу.
`test_email_verification.py` стережёт, что до подтверждения почты пользователя не существует.
`test_secret_encryption.py` стережёт, что токены соцсетей не лежат в базе открытым текстом.
`test_settings_multi_group.py` стережёт, что интеграция подключается больше чем к одной группе.
`test_upload_access.py` стережёт, что файлы не отдаются без подписи и что подпись не оседает в базе.
`test_scheduler.py` стережёт автопубликацию: срок, двойную отправку и протухшие посты.

## Известные проблемы

1. ~~Глобальные эндпоинты без авторизации.~~ Исправлено — см. «Авторизация» выше.
2. ~~Дублирование схемы init_db ↔ alembic.~~ Исправлено — источник правды только alembic.
3. ~~Нет тестов и линтеров.~~ Исправлено — см. «Проверки» выше.
4. ~~Открытая регистрация давала доступ к чужой группе.~~ Исправлено — автовступления нет.
5. ~~Почта не подтверждалась, `email_verifications` не использовалась.~~ Исправлено —
   см. «Регистрация в два шага» выше.
6. ~~Токены соцсетей в базе открытым текстом.~~ Исправлено — см. «Секреты в базе» выше.
7. ~~`vk_settings.id` / `tg_settings.id` были `INTEGER DEFAULT 1` без последовательности,
   из-за чего интеграция подключалась только к одной группе (вторая падала с
   UniqueViolation).~~ Исправлено миграцией `c7f2a5b30d84`; id=1 навсегда закреплён
   за глобальными настройками, последовательность стартует с 2.
8. ~~`/uploads` раздавался StaticFiles без авторизации.~~ Исправлено — см.
   «Загрузки отдаются только по подписанной ссылке» выше.
9. ~~Загрузки терялись при каждой выкатке.~~ Исправлено — том на Railway + `UPLOAD_DIR`.
10. ~~Отложенные посты никогда не публиковались — планировщика не было вовсе.~~
    Исправлено, см. «Планировщик отложенных постов» выше.

Осталось нерешённым:

- Миграции и планировщик запускаются в startup-хуке приложения. При масштабировании
  больше чем в один инстанс миграции правильнее вынести в release-команду Railway.
  Планировщик к нескольким инстансам готов (заявка через `publish_attempts`).
- Загрузки лежат на диске контейнера — на Railway без volume теряются при редеплое.
- `@app.on_event("startup")` устарел, FastAPI просит lifespan-хендлеры.

## Даты в БД

`posts.created_at / scheduled_at / published_at`, `users.created_at` и прочие «временные»
поля — это **TEXT** в формате `YYYY-MM-DDTHH:MM`. Сортировка лексикографическая совпадает
с хронологической, поэтому `ORDER BY` работает, но арифметика по датам и таймзоны — нет.
Фильтры по периодам собираются строковыми сравнениями (`BETWEEN`, `LIKE 'YYYY-MM-DD%'`).
