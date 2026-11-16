# Germany Assistant — Telegram-бот + Mini App для украинцев в Германии

Статус: **этап A готов** (фундамент). Этапы B–E — см. `docs/PROGRESS.md`.

## Что работает сейчас

| Функция | Статус |
|---|---|
| /start, выбор языка (uk/ru), регистрация из 5 шагов | ✅ работает |
| Главное меню (8 разделов), /menu, /help, /settings, /privacy | ✅ работает |
| Профиль: просмотр, изменение, смена языка, согласие на объявления | ✅ работает |
| /export_my_data (JSON), /delete_my_data (с подтверждением) | ✅ работает |
| Справочник официальных ссылок (11 тем, хранится в БД) | ✅ работает |
| Работа / Жильё — ссылки на официальные сайты | ✅ временный вариант |
| Документы, Переводчик, AI-помощник | 🛠 честное сообщение «в разработке», без выдуманных ответов |
| Mini App: главная, профиль, справочник, удаление данных | ✅ работает (нужен HTTPS-адрес) |
| Админ: /admin, /stats, /block, /unblock | ✅ работает (только ADMIN_IDS) |
| Обезличенная аналитика событий | ✅ работает |
| Rate limiting, централизованная обработка ошибок, логи без личных данных | ✅ работает |
| Подписки и оплата | ⏳ этап D |

## Быстрый старт (локально, без Docker)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # впишите BOT_TOKEN и ADMIN_IDS
alembic upgrade head          # создаёт таблицы (SQLite в ./data)
python -m app.main            # бот (long polling) + Mini App на :8080
```

Тесты: `pytest -q`

## Запуск через Docker (сервер)

```bash
cp .env.example .env          # BOT_TOKEN, ADMIN_IDS, ANALYTICS_SALT, POSTGRES_PASSWORD
docker compose up -d --build  # PostgreSQL + Redis + бот, миграции выполняются автоматически
docker compose logs -f bot
```

Сервер лучше брать в ЕС (DSGVO): например, Hetzner, IONOS, netcup.

## Деплой на Render (рекомендуется)

1. render.com → **New → Blueprint** → выберите этот репозиторий. Render прочитает `render.yaml`.
2. Введите `BOT_TOKEN` и `ADMIN_IDS`, когда Render их запросит.
3. **Apply.** Render создаст базу PostgreSQL и сервис во Франкфурте, выдаст адрес `https://….onrender.com`.
4. Бот сам возьмёт этот адрес для Mini App и добавит кнопку в меню чата.

Каждый новый коммит в репозиторий разворачивается автоматически.

## Создание бота в BotFather

1. Откройте @BotFather → `/newbot` → имя и username.
2. Скопируйте токен в `BOT_TOKEN` в `.env`. Токен никогда не коммитьте.
3. Если токен где-то засветился — `/revoke` в BotFather и новый токен в `.env`.
4. `ADMIN_IDS`: ваш числовой Telegram ID (узнать: @userinfobot).

## Mini App

Telegram открывает Mini App только по **HTTPS**.

- **Сервер:** поставьте перед портом 8080 Caddy (сертификат выдаётся автоматически):
  ```
  bot.example.de {
      reverse_proxy localhost:8080
  }
  ```
  Затем `WEBAPP_URL=https://bot.example.de` в `.env` и перезапуск. Бот сам добавит кнопку приложения в меню чата.
- **Для теста без сервера:** `cloudflared tunnel --url http://localhost:8080` выдаст временный https-адрес.

Безопасность: каждый запрос Mini App подписан Telegram (`initData`), сервер проверяет подпись токеном бота — пользователь видит и меняет только свой профиль.

## Webhook или long polling

Сейчас используется **long polling** — проще, не нужен публичный адрес для самого бота. Webhook имеет смысл при большой нагрузке; переход — отдельная задача.

## AI-ключ (этап B)

Бизнес-логика зависит только от интерфейса `app/services/ai/base.py`. Провайдер выбирается в `.env` (`AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`). Пока `AI_PROVIDER=none`, бот честно говорит, что AI не подключён. Перед подключением: договор обработки данных (DPA) с провайдером и, по возможности, обработка в ЕС.

## Структура

```
app/
  config.py              настройки из .env
  main.py                запуск бота + Mini App
  i18n/locales/*.json    все тексты (uk, ru; добавить de = новый файл)
  bot/handlers/          start (регистрация), menu, settings (профиль/данные), common
  bot/keyboards/         клавиатуры
  bot/middlewares/       сессия БД + пользователь, rate limit
  admin/                 админ-команды
  database/              модели, репозитории
  data/                  земли, уровни, каталог официальных источников
  services/ai/           интерфейс AI-провайдера (этап B)
  webapp/                FastAPI + static/index.html (Mini App)
migrations/              Alembic
tests/                   pytest (сквозные сценарии бота + API Mini App)
docs/                    план, черновик Datenschutz
```

## Что нужно получить

| Что | Зачем | Когда |
|---|---|---|
| Токен BotFather | бот | ✅ есть |
| Ваш Telegram ID | админ-команды | сейчас |
| Сервер в ЕС + домен | постоянная работа, Mini App | до запуска |
| Ключ AI-провайдера + DPA | документы, перевод, AI | этап B |
| Сервис распознавания речи | голосовые | этап B |
| Доступ к API вакансий | поиск работы | этап C |
| Юрист: Impressum, Datenschutz | публичный запуск | до запуска |
