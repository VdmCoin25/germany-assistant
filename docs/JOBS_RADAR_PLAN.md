# Jobs Source Radar — план (J0 → J1–J4)

Статус: **план одобрен 2026-11-16**. Ветка `feat/jobs-source-radar`. Факты J0 проверены 2026-11-16, ссылки — в конце.

Принятые решения (2026-11-16):
- D1 — остаёмся на Render (вариант A). Worker и платную базу владельцы подключают сами, `render.yaml` в этой ветке не меняется.
- D2 — сейчас классификатор на правилах (`RuleClassifier`), LLM через `AIProvider` подключаем позже. Правила Telegram (§1.5) владельцы блокером не считают.
- D3 — без ARQ и Redis: обработка сразу в мониторе, лимиты и журнал — в Postgres.
- D4 — список переносимых файлов одобрен.
- J3 — письмо в BA отложено, J3 не делаем.
- Аккаунт-монитор добавят позже; до этого всё на моках.

Цель первого запуска: 50 активных чатов (≥ 1 пост в день) и 30 агентств с рабочим контактом.

## 0. Итоги J0 (коротко)

| # | Вопрос | Вывод |
| --- | --- | --- |
| 1 | Где живёт монитор | Бесплатных фоновых процессов у Render нет. Монитор в web-сервисе на free не работает (засыпает, исходящее соединение Telethon трафиком не считается). Варианты и цены — решение D1. **Бесплатная база Render живёт 30 дней** (+14 дней на апгрейд, потом удаляется) — касается живого бота уже сейчас, `render.yaml`: `plan: free`. |
| 2 | Перенос из leadgen | Копирование с адаптацией. Общий пакет — позже; код уже разделён через инъекции (`join_fn`, `clock`, `IncomingMessage`), извлечение будет механическим. |
| 3 | Telethon | `telethon==1.45.0` (2026-09-10), ветка v1, оригинал переехал на Codeberg. Лимит 500 каналов/супергрупп на аккаунт (`CHANNELS_TOO_MUCH`). Документированных лимитов на вступления в день и на `resolveUsername` **нет**. Метаданные без вступления подтверждены только для инвайт-ссылок (`messages.checkChatInvite`: title, about, participants_count). Работают ли `GetFullChannel` и чтение истории публичного чата **без вступления** — не подтверждено, только эксперимент. Поиск чатов по слову: подтверждён только `contacts.search` (подстрока username) и `channels.searchPosts` (посты публичных каналов, полнотекстовый — частично платный). Используем только ссылки и @упоминания. |
| 4 | Jobbörse BA | Технически работает `GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`, `X-API-Key: jobboerse-jobsuche`. Ответ отличается от документации (`ergebnisliste`, `referenznummer`, `firma`). Признака Zeitarbeit в ответе нет, есть только фильтр `zeitarbeit` в запросе. **Условия: неясно.** Nutzungsbedingungen §10–11 не открылись (404), Impressum требует согласия BA на повторное использование контента, контакты закрыты captcha «от несанкционированного краулинга». → **J3 заблокирована** до письма в BA. |
| 5 | Правила Telegram | API Terms §1.4: нельзя действовать от имени пользователя без его ведома, нельзя трогать статусы «прочитано». §1.5 (проверено по оригиналу): запрещено использовать данные Telegram, чтобы «train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models». Аккаунты неофициальных клиентов «automatically put under observation»; за флуд и спам — перманентный бан. Официальных цифр «сколько вступлений в день безопасно» нет. |
| 6 | AI-провайдер | Прямой Anthropic API обработку в ЕС не даёт (только `us`/`global`). Обработка в ЕС: Haiku через AWS Bedrock eu-central-1, Gemini Flash-Lite на Vertex `eu`, OpenAI EU (для «eligible»-организаций), Mistral (EU-компания, EU-хостинг API официально не подтверждён). Цена за 1000 сообщений ~ $0.06–0.13. См. D2. |

## 1. Решения (варианты, которые сравнивали)

### D1. Хостинг монитора и фоновых задач (траты → решаете вы с Вадимом)

| Вариант | Цена в месяц | Плюсы | Минусы |
| --- | --- | --- | --- |
| **A. Render Background Worker** (Starter 512 MB) + платная Render Postgres | $7 + $6 + $0.30/GB ≈ **$13–14** | Тот же регион Frankfurt, внутренняя сеть до базы, ничего нового в обслуживании, деплой из той же ветки | Платно оба сервиса |
| **B. VPS Hetzner** (CX23, 2 vCPU / 4 GB), Postgres и монитор в `docker-compose.yml` на VPS; бот на Render ходит в базу по внешнему адресу с TLS | **€5.99** без НДС | Дешевле, ресурсов больше | Бэкапы, обновления и защита базы на нас; у free web-сервиса Render нет фиксированных исходящих IP — allow-list не сделать; новый хостинг |

**Рекомендация: A.** Платная база нужна в любом случае: бесплатная удаляется через 30 + 14 дней. Предложение для `render.yaml` (сам файл не трогаю):

```yaml
  - type: worker
    name: germany-assistant-radar
    runtime: python
    region: frankfurt
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.jobs_radar.monitor   # no migrations here: the web service runs them
    envVars:
      - key: JOBS_RADAR_ENABLED
        value: "false"
      - key: TG_API_ID
        sync: false
      - key: TG_API_HASH
        sync: false
      - key: TG_SESSION
        sync: false
      - key: DATABASE_URL
        fromDatabase: { name: germany-assistant-db, property: connectionString }
# databases: germany-assistant-db → plan: basic-256mb (or current cheapest paid)
```

До выбора код пишется и тестируется локально. Монитор — отдельная точка входа `python -m app.jobs_radar.monitor`, бот её не запускает.

### D2. Классификатор и AI-провайдер (траты и DPA → решаете вы с Вадимом)

**Решение:** интерфейс `JobClassifier`. Сейчас реализуем `RuleClassifier` (префильтр + веса ключевых слов и шаблонов, без внешних вызовов), `JOBS_CLASSIFIER=rules`. `AIClassifier` через `AIProvider` — следующим шагом, когда выберут провайдера (провайдер по умолчанию `NoProvider`).

Кандидаты для LLM с обработкой в ЕС:

| Провайдер / модель | $ за 1000 сообщений* | ЕС | DPA |
| --- | --- | --- | --- |
| Claude Haiku 5.5 через AWS Bedrock eu-central-1 | ~0.105 | да (EU-эндпоинт, +10%) | условия AWS |
| Gemini 2.5 Flash-Lite, Vertex AI `eu` | ~0.087 | да | да, только платный тариф |
| Mistral Ministral 8B / Small 4 | ~0.09 / 0.13 | EU-компания, хостинг API официально не подтверждён | публичный DPA, отказ от обучения оформить явно |
| OpenAI gpt-5-nano, проект EU | ~0.06 | для «eligible»-организаций | страница не открылась |

\* 550 входных + 80 выходных токенов на сообщение. Украинский текст обычно даёт больше токенов, реальная цена выше. Рассуждающие модели (Haiku 5.5, gpt-5-nano): включить минимальный effort, иначе платим за рассуждения.

### D3. Очередь и счётчики: без ARQ

В leadgen очередь ARQ на Redis, счётчики вступлений — тоже в Redis. Здесь Redis на Render не подключён.

- **Рекомендация:** без ARQ и без Redis. Монитор обрабатывает сообщение сразу в процессе (префильтр → классификатор → запись результата). После простоя догоняет пропущенное из Telegram по `last_message_id` чата (catchup из leadgen). Лимиты вступлений и метаданных — в таблице `job_radar_actions` в Postgres. Текст сообщений в базу не пишем вообще — это проще и соответствует правилу хранения данных.
- Вариант Б: перенести ARQ и добавить Redis на Render (Key Value, платный для постоянной работы). Не рекомендую: больше движущихся частей ради ~100 чатов.

### D4. Что переносим из leadgen (на ваше «ок»)

Только общий код. **Не переносим:** `core/prompts.py` (все промпты продаж), всё в `core/llm.py`, кроме каркаса `classify`, `listener/portrait.py` и `listener/profile.py` (читают bio и профили авторов — запрещено), `seed.sql` и `seed_terms.py` с ключевыми словами, фикстуры с реальными сообщениями, сборщики конкретных сайтов, `.env` и конфиги.

| Из leadgen | Сюда | Адаптация |
| --- | --- | --- |
| `services/core/src/core/tglinks.py` + тест | `app/jobs_radar/tglinks.py`, `tests/test_jobs_radar_links.py` | без изменений логики |
| `services/core/src/core/prefilter.py` + тест (`test_prefilter_seed.py` не берём) | `app/jobs_radar/prefilter.py` | список слов — из таблицы/конфига |
| `services/core/src/core/llm.py` → только `_neutralize`, `_wrap`, разбор JSON и ошибок | `app/jobs_radar/classifier.py` | вызов через `AIProvider.complete()` |
| `services/listener/src/listener/telegram.py` | `app/jobs_radar/telegram.py` | — |
| `…/listener/state.py` | `app/jobs_radar/state.py` | asyncpg → `async_sessionmaker`, без `owner_id` |
| `…/listener/handler.py` | `app/jobs_radar/handler.py` | без автора сообщения; вместо постановки в ARQ — прямой вызов обработки |
| `…/listener/catchup.py` | `app/jobs_radar/catchup.py` | запросы через SQLAlchemy; тексты уведомлений — в i18n |
| `…/listener/joiner.py` | `app/jobs_radar/joiner.py` | счётчики Redis → таблица; вступает только в `approved` |
| `…/listener/main.py` | `app/jobs_radar/monitor.py` | без `ProfileConsumer`, heartbeat, Sentry, ARQ и pubsub |
| `…/tests/test_listener_readonly.py` | `tests/test_jobs_radar_readonly.py` | запрещённый список расширяем: `GetFullUserRequest`, `GetCommonChatsRequest`, `GetParticipantsRequest`, `iter_participants`, `get_participants` |
| `services/worker/src/worker/collectors/base.py` (хелперы и `http_client`) | `app/jobs_radar/collectors/base.py` (только J3) | без repo/redis/metrics, свой User-Agent |
| `scripts/telegram_login.py` | `scripts/telegram_login.py` | `app.config`; сессия выводится только в консоль, не пишется в файлы |
| `scripts/eval_classifier.py` (только метрики) | `scripts/eval_jobs_classifier.py` | новая синтетическая фикстура |

Новые зависимости в `requirements.txt`: `telethon==1.45.0`; `httpx` перенести из dev в основные — только для J3.

## 2. Архитектура

- Пакет `app/jobs_radar/`. Бот подключает только админ-роутер радара, и только при `JOBS_RADAR_ENABLED=true`. С выключенным флагом `build_dispatcher` такой же, как сейчас (это проверяет тест).
- Монитор: `python -m app.jobs_radar.monitor`. При выключенном флаге пишет в лог и сразу завершается. Миграции не запускает.
- Telegram-аккаунт монитора только читает, плюс вступает в одобренные чаты. Не вызывает send/reply/forward/edit/delete/mark_read/typing, не читает профили и участников. Это закреплено тестом на исходный код.
- Уведомления админам (дайджест агентств, «вступил», «заблокирован FloodWait», «аккаунт заморожен») шлёт **бот** (aiogram, `ADMIN_IDS`), а не аккаунт-монитор. Монитор отправляет их через Bot API токеном бота — только в чаты из `ADMIN_IDS`.
- Хранение: тексты сообщений не храним. `job_signals` — только ссылка, тип, город, профессия, язык, удаление через 14 дней (ежедневная чистка в мониторе + проверка в тесте). Автора сообщения не храним вообще.
- Имена: новые модели с префиксом `Job…Radar`/`job_*`, чтобы не путать с существующими `InfoSource`, `Employer`, `Vacancy` (биржа работы бота). Агентства радара — отдельная таблица: это потенциальные клиенты, а не зарегистрированные работодатели.

### Таблицы (миграция `0004_jobs_radar.py`, только добавление)

- `job_chats`: `id`, `tg_chat_id` (unique, null для кандидатов), `username` (unique, null), `invite_hash`, `title`, `members`, `posts_per_day_7d`, `ads_allowed` (`unknown|yes|no`), `admin_contact` (из публичного описания чата), `language`, `city`, `land`, `discovered_from` (`seed|link|mention`), `discovered_via_chat_id`, `status` (`candidate|approved|joined|rejected`), `join_error`, `score`, `last_message_id`, `last_checked_at`, `created_at`.
- `job_chat_daily`: `chat_id`, `day`, `posts` (PK `chat_id+day`) — для среднего за 7 дней; строки старше 30 дней удаляются.
- `job_radar_actions`: `kind` (`join|metadata`), `chat_id`, `at`, `result` — дневные лимиты и журнал.
- `job_keywords`: `term`, `lang`, `kind` (`include|exclude`), `active` — список префильтра, заполняется сидом из `app/data/jobs_radar_keywords.py`.
- `job_signals` (J2): `id`, `chat_id`, `message_link`, `kind` (`seeker_question|agency_vacancy|chat_rules`), `city`, `profession`, `language`, `confidence`, `created_at`; удаление через 14 дней.
- `job_agencies` (J2): `id`, `name`, `name_norm`, `domain`, `phone_norm`, `email`, `website`, `source` (`telegram|jobboerse`), `first_seen_at`, `last_seen_at`, `signals_count`, `digest_sent_at`. Дедуп по `name_norm`, `domain`, `phone_norm`. Телефон и email — только из текста вакансии, как деловой контакт.
- J3 (если разблокируют): `job_ba_vacancies` — отдельной миграцией.

### Скоринг чата (J1)

`score = активность (posts_per_day_7d, с потолком) + размер (log members) + доля jobs-сигналов за 7 дней + бонус за язык uk/ru и город в Германии − штраф при ads_allowed=no`. Веса — в конфиге, формула покрыта тестами. «Активный» чат = `posts_per_day_7d ≥ 1`.

## 3. Задачи

Порядок: **J1.1 → (J1.2 ∥ J2) → J4**. J3 заблокирована. J1.2 и J2 общих файлов не имеют, кроме `app/config.py` и `.env.example`: эти правки делаются в J1.1 заранее.

### J1.1 Каталог: данные, ссылки, импорт, админ-команды

Файлы: `app/config.py` (все новые настройки радара сразу), `.env.example`, `app/database/models.py`, `migrations/versions/0004_jobs_radar.py`, `app/database/repositories/jobs_radar.py`, `app/jobs_radar/{__init__,tglinks,scoring,discovery}.py`, `app/jobs_radar/admin.py` (роутер), `app/main.py` (подключение роутера только при флаге), `app/data/jobs_radar_keywords.py`, `scripts/import_job_chats.py`, `app/i18n/locales/{uk,ru}.json`, `tests/test_jobs_radar_catalog.py`, `tests/fixtures/job_chats_sample.csv`.

- `/add_job_chat <t.me-ссылка|@username>` → `approved` (добавлено админом вручную).
- `/job_candidates` → список кандидатов с кнопками «одобрить / отклонить» (callback только для `ADMIN_IDS`).
- `discovery.extract(text, source_chat)` → новые `candidate` с `discovered_from=link|mention`; дедуп по username/invite/chat id. Ссылка или @упоминание может указывать на частного человека, поэтому кандидат создаётся с `entity_type=unknown`; монитор (J1.2) проверяет тип и **удаляет** строку, если это пользователь, а не канал/группа. `/job_candidates` не показывает `entity_type=user`.
- Импорт CSV (`username,title,city,land,language,ads_allowed`) → `seed`/`approved`, повторный запуск не создаёт дублей.

**Готово, когда:** `pytest -q` зелёный, включая тесты на разбор ссылок, дедуп, скоринг, админ-команды (не-админ получает отказ) и «флаг выключен → роутер не подключён». `alembic upgrade head` на локальной базе проходит, после импорта `tests/fixtures/job_chats_sample.csv` (10 строк, вымышленные чаты) в базе 10 ожидаемых строк, повторный импорт — всё ещё 10.

### J1.2 Монитор (Telethon, только чтение)

Файлы: `requirements.txt` (`telethon==1.45.0`), `app/jobs_radar/{telegram,state,handler,catchup,joiner,metadata,monitor}.py`, `scripts/telegram_login.py`, `tests/test_jobs_radar_monitor.py`, `tests/test_jobs_radar_readonly.py`.

- Слушает новые сообщения только из `joined`-чатов; считает посты по дням; передаёт текст в `discovery` и (после J2) в классификатор; обновляет `last_message_id`.
- Catchup после простоя (по `last_message_id`, с ограничением глубины).
- Joiner: только `approved`, дневной лимит `JOBS_JOIN_DAILY_CAP` (по умолчанию 3), случайная пауза 1–2 часа между вступлениями, остановка на `CHANNELS_TOO_MUCH` / `FROZEN_METHOD_INVALID` с уведомлением админам. `INVITE_REQUEST_SENT` — состояние «ждём», не ошибка.
- Метаданные: `get_entity` + `GetFullChannelRequest` (участники, описание, привязанный чат), для инвайт-ссылок `CheckChatInviteRequest`. Лимит `JOBS_METADATA_DAILY_CAP` (по умолчанию 50) и бэкофф. FloodWait: при `seconds` больше порога задача откладывается, повтор раньше срока запрещён.
- Контакт админа и `ads_allowed` — из публичного описания чата (простые правила: «реклама», «реклама заборонена», @username в описании).

**Готово, когда:** все тесты на моках Telethon зелёные: лимиты и паузы (инъекция `clock/sleep/rand`), FloodWait, catchup, «вступает только в approved». Тест read-only проходит. Монитор с `JOBS_RADAR_ENABLED=false` сразу выходит с кодом 0. Настоящих сессий нет.

### J2. Классификатор

Файлы: `app/jobs_radar/{prefilter,classifier,rules,agencies,digest}.py`, `app/services/ai/base.py` (только если нужен общий хелпер JSON; провайдеры не добавляем), `scripts/eval_jobs_classifier.py`, `tests/fixtures/jobs_messages.jsonl` (40 синтетических размеченных сообщений uk/ru/de без реальных людей, телефонов и ников), `tests/test_jobs_radar_classifier.py`.

- Префильтр по `job_keywords` (uk/ru/de, include/exclude).
- Интерфейс `JobClassifier` и `RuleClassifier` (по умолчанию, `JOBS_CLASSIFIER=rules`). `AIClassifier` (через `AIProvider`, текст в `<message>` с нейтрализацией, ответ — JSON с проверкой схемы) — отдельным шагом J2b после выбора провайдера.
- Метки `seeker_question|agency_vacancy|chat_rules|noise` + город, профессия, язык, confidence; для вакансии — компания, сайт, рабочий контакт.
- Запись: `job_signals` (без текста), `job_agencies` (дедуп). Ежедневная чистка сигналов старше 14 дней.
- Дневной дайджест новых агентств админам (через бота). По соискателям ничего не шлём.

**Готово, когда:** внешних вызовов нет. На фикстуре `RuleClassifier` даёт precision ≥ 0.85 для `agency_vacancy` и ≥ 0.80 для `seeker_question`; скрипт оценки печатает таблицу метрик. Тесты на дедуп агентств и 14-дневную чистку зелёные. Реальный прогон через API — только после вашего «ок».

### J3. Коллектор Jobbörse — **отложено**

Не начинаем, пока BA письменно не подтвердит, что такой сбор допустим. Письмо отложено (решение 2026-11-16). Черновик вопросов в Account- und Allianzpartnermanagement BA (`service-haus.vam-accountmgmt@arbeitsagentur.de`):
1. Разрешён ли автоматический доступ к `rest.arbeitsagentur.de/jobboerse/jobsuche-service` с публичным ключом, какие лимиты?
2. Можно ли хранить название работодателя, должность, город, `refnr` и дату и использовать их, чтобы связываться с работодателями и агентствами как с B2B-контактами?
3. Есть ли официальный интерфейс на чтение или лицензия для Stellenbörsen и партнёров?
4. Актуальный текст Nutzungsbedingungen Jobbörse (§10–11).

Если разрешат: `/pc/v6/jobs`, `size=100`, последовательные запросы с паузой ≥ 2 с, несколько десятков запросов в день, признак агентства — разница запросов `zeitarbeit=true/false`. `jobdetails` не запрашиваем, captcha не трогаем, контакты и ФИО не храним.

### J4. Выгрузка

Файлы: `app/jobs_radar/admin.py`, `app/admin/handlers.py` (только `/stats`), `app/database/repositories/jobs_radar.py`, `app/i18n/locales/{uk,ru}.json`, `tests/test_jobs_radar_export.py`.

- `/job_sources` — топ-50 по `score`, `/job_agencies` — топ-30, кнопка «CSV» отправляет файл (UTF-8 с BOM, разделитель `;` для Excel).
- `/stats`: счётчики радара (чатов по статусам, активных, сигналов за 7 дней, агентств) — только при включённом флаге.

**Готово, когда:** на локальной базе с фикстурами команды отдают ожидаемое число строк в нужном порядке, CSV читается `csv.reader` и открывается в Excel; при выключенном флаге `/stats` не изменился.

### J5. Демо без аккаунта

Файлы: `app/jobs_radar/demo.py`, `app/jobs_radar/demo_fake.py`, `app/data/jobs_radar_demo.py`, `tests/test_jobs_radar_demo.py`.

Запуск (Windows, из корня репозитория, виртуальное окружение уже создано):

```
.venv\Scripts\python.exe -m app.jobs_radar.demo [--out ПАПКА] [--days N]
```

`--out` — куда положить `sources.csv` и `agencies.csv` (по умолчанию новая временная папка, путь печатается в конце), `--days` — сколько суток симулировать (по умолчанию 3). Занимает несколько секунд.

Что показывает (по шагам, по-русски): импорт и одобрение чатов; вступления по суткам (лимит 3, пауза, FloodWait один раз, заявка по закрытой ссылке, ссылка на человека удаляется); метаданные и оценка чатов; живые сообщения и догоняющее чтение; таблицу классификации (метка и причина по каждому сообщению); найденные агентства; дайджест, который получили бы админы; чистку сигналов старше 14 дней; итоговые счётчики (как в `/stats`) и пути к CSV.

Это полностью оффлайн: настоящий монитор (`Monitor`, `Joiner`, `MetadataCollector`, `catch_up_all`, `Pipeline`, классификатор) работает с подставным клиентом Telegram в памяти и подставным ботом, который только запоминает сообщения админам. Аккаунт, `TG_*`, `BOT_TOKEN`, `.env` и сеть не нужны; `DATABASE_URL` и `JOBS_RADAR_ENABLED` из окружения игнорируются. База — одноразовый SQLite-файл во временной папке, удаляется в конце. Время симулируется, ждать суток не нужно. Данные (чаты, компании, телефоны вида `+49 30 0000 00xx`) выдуманные, лежат в `app/data/jobs_radar_demo.py`. Подставной клиент не умеет отправлять, писать и отмечать прочитанным; тест read-only проверяет и его.

## 4. Новые переменные окружения (все в `.env.example`)

`JOBS_RADAR_ENABLED=false`, `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` (StringSession, секрет), `JOBS_JOIN_DAILY_CAP=3`, `JOBS_METADATA_DAILY_CAP=50`, `JOBS_CLASSIFIER=rules`, `JOBS_SIGNAL_RETENTION_DAYS=14`, `JOBS_DIGEST_HOUR=9`. Для LLM — уже существующие настройки `AI_PROVIDER` и т. п. в `app/config.py`.

## 5. Что нужно от владельцев позже

1. **Независимо от радара:** проверить в Render дату создания `germany-assistant-db` — бесплатная база удаляется через 30 + 14 дней.
2. Перед включением: Render worker и платная база, переменные окружения из раздела 4.
3. Новый Telegram-аккаунт для монитора и свой `api_id` (my.telegram.org). Вход — сами через `scripts/telegram_login.py`.
4. Выбор LLM-провайдера и DPA — для `AIClassifier`.
5. До включения на живых данных: эксперимент на одном публичном чате — читается ли он без вступления.

Тексты админ-команд — по образцу `app/admin/` (на русском прямо в коде, только для `ADMIN_IDS`). Тексты для пользователей бота — в `uk.json`/`ru.json`.

## Источники (открыты 2026-11-16)

- Render: https://render.com/docs/free, https://render.com/pricing.md, https://render.com/docs/background-workers, https://render.com/docs/postgresql-creating-connecting
- Hetzner: https://www.hetzner.com/cloud/cost-optimized/
- Telethon: https://pypi.org/pypi/Telethon/json, https://codeberg.org/Lonami/Telethon, https://docs.telethon.dev/en/stable/concepts/errors.html
- Telegram API: https://core.telegram.org/api/terms, https://core.telegram.org/api/obtaining_api_id, https://core.telegram.org/api/config, https://core.telegram.org/api/invites, https://core.telegram.org/method/contacts.search, https://core.telegram.org/method/channels.searchPosts, https://core.telegram.org/method/channels.getFullChannel, https://core.telegram.org/method/messages.checkChatInvite, https://telegram.org/faq_spam
- Jobbörse: https://github.com/bundesAPI/jobsuche-api (README, openapi.yaml, issues 23/68/69), https://www.arbeitsagentur.de/impressum, https://www.arbeitsagentur.de/en/privacy-notice, https://jobboerse.arbeitsagentur.de/vamJB/hilfe/de/AS/unbetreut/1128.html, https://www.arbeitsagentur.de/unternehmen/arbeitskraefte/hr-ba-xml-schnittstelle
- AI: https://platform.claude.com/docs/en/about-claude/pricing, https://platform.claude.com/docs/en/manage-claude/data-residency, https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock, https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations, https://aistudio.google.com/docs/pricing, https://mistral.ai/pricing, https://legal.mistral.ai/terms/data-processing-addendum, https://developers.openai.com/api/docs/pricing, https://developers.openai.com/api/docs/guides/data-residency
