# План реализации: Price Monitor Pro

## Обзор

Пошаговая реализация Price Monitor Pro — продвинутой системы мониторинга цен. Миграция из текущего прототипа (плоская структура, одна таблица `watches`) в модульную многопользовательскую платформу с REST API v1, Telegram-ботом, веб-дашбордом, визуальным селектором, макросами, группами сравнения и мультиканальными уведомлениями. Стек: Python, FastAPI, asyncpg + SQLAlchemy async, Playwright, PostgreSQL.

## Задачи

- [x] 1. Инициализация структуры проекта и конфигурация
  - [x] 1.1 Создать модульную структуру каталогов `app/` с пакетами: models, services, api, bot, web, migrations
    - Создать `app/__init__.py`, `app/models/__init__.py`, `app/services/__init__.py`, `app/api/__init__.py`, `app/bot/__init__.py`, `app/web/__init__.py`, `app/migrations/`
    - Создать каталоги `templates/`, `static/`, `static/js/`
    - _Требования: 19.1_

  - [x] 1.2 Реализовать `app/config.py` — конфигурация через Pydantic Settings
    - Определить класс `Settings(BaseSettings)` с полями: DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, POLL_INTERVAL, PORT, API_SECRET_KEY, PROXY_URL, CORS_ORIGINS
    - Валидация: DATABASE_URL обязателен, при отсутствии — ошибка "DATABASE_URL is required"
    - _Требования: 18.2, 18.3_

  - [x] 1.3 Реализовать `app/database.py` — async подключение к БД
    - Настроить asyncpg + SQLAlchemy async engine и session factory
    - Connection pooling: max_size=20
    - Реализовать reconnect с экспоненциальной задержкой (до 5 попыток)
    - _Требования: 20.1, 20.5_

  - [x] 1.4 Обновить `requirements.txt` с зависимостями
    - fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, python-telegram-bot, playwright, apscheduler, pydantic-settings, python-jose[cryptography], cachetools, aiohttp, aiosmtplib, cssselect, Jinja2, python-multipart
    - _Требования: 18.1_

- [x] 2. Модели данных и миграции БД
  - [x] 2.1 Создать SQLAlchemy модели в `app/models/`
    - `user.py`: User (id, telegram_chat_id, username, timezone, quiet_hours_start/end, digest_frequency, digest_time, digest_day_of_week, default_check_interval, created_at, updated_at), APIKey (id, user_id, key_hash, key_prefix, name, is_active, last_used_at, created_at)
    - `monitor.py`: Monitor (все 20+ полей из схемы), MonitorTemplate (domain, store_name, css_selector, xpath_selector, currency, availability_patterns, created_by, is_system)
    - `price.py`: PriceHistory (id, monitor_id, price, raw_text, availability_status, screenshot_id, recorded_at), Screenshot (id, monitor_id, image_data, created_at)
    - `alert.py`: AlertCondition (id, monitor_id, type, value, operator, parent_condition_id, cooldown_seconds, is_active, last_triggered_at), AlertLog (id, monitor_id, user_id, condition_id, alert_type, message, old_price, new_price, change_pct, created_at), NotificationChannel (id, user_id, monitor_id, channel_type, config, is_active)
    - `comparison.py`: ComparisonGroup, ComparisonGroupMonitor
    - `macro.py`: Macro (id, monitor_id, step_order, action_type, selector, params)
    - Таблицы связей: monitor_tags, comparison_group_monitors, queued_alerts
    - _Требования: 1.7, 4.8, 5.6, 12.1, 13.1, 21.1, 22.5, 23.2, 24.1_

  - [x] 2.2 Создать SQL-миграцию `app/migrations/001_full_schema.sql`
    - Полная схема: 14 таблиц (users, api_keys, monitors, price_history, screenshots, alert_conditions, alerts_log, notification_channels, tags, monitor_tags, comparison_groups, comparison_group_monitors, macros, monitor_templates, queued_alerts)
    - ALTER TABLE watches RENAME TO monitors + добавление новых колонок
    - Все индексы: idx_monitors_user, idx_monitors_normalized_url, idx_monitors_active, idx_ph_monitor_time, idx_alerts_user, idx_alerts_monitor, idx_api_keys_hash, idx_templates_domain и др.
    - _Требования: 18.5, 27.5_

  - [x] 2.3 Реализовать автоматический запуск миграций при старте приложения
    - Функция `run_migrations()` в `app/database.py` — выполнение SQL-файлов из `app/migrations/` по порядку
    - Создание таблицы `schema_migrations` для отслеживания выполненных миграций
    - _Требования: 18.5_


- [ ] 3. Контрольная точка — Структура проекта и БД
  - Убедиться, что все модели создаются без ошибок, миграции выполняются, подключение к БД работает. Задать вопросы пользователю при необходимости.

- [x] 4. Сервис аутентификации и пользователей
  - [x] 4.1 Реализовать `app/services/auth_service.py`
    - `get_or_create_user(telegram_chat_id)` — создание пользователя при первом взаимодействии
    - `generate_api_key(user_id)` — генерация 64-символьного ключа через `secrets.token_hex(32)`, хранение sha256-хеша
    - `authenticate_api_key(key)` — поиск пользователя по хешу ключа
    - `create_session_token(user_id)` — JWT-токен (exp: 24h) через python-jose
    - `verify_session_token(token)` — верификация JWT
    - _Требования: 16.1, 16.2, 16.3, 16.5_

  - [ ]* 4.2 Написать unit-тесты для AuthService
    - Тест создания пользователя, генерации API-ключа, аутентификации, JWT-токенов
    - Тест изоляции данных пользователей
    - _Требования: 16.1, 16.2, 16.3, 16.4_

- [x] 5. Сервис парсинга цен
  - [x] 5.1 Реализовать `app/services/price_parser.py`
    - `PriceParser.parse(text, currency)` — парсинг цены из текста: удаление символов валют, нормализация пробелов (nbsp, thin space), определение разделителя тысяч vs десятичного, извлечение числового значения
    - Поддержка форматов: "1 299,90 ₽", "$12.99", "12,99 €", "1.299,90", "1,299.90"
    - `PriceParser.format_price(value, currency)` — форматирование числа обратно в текст с символом валюты
    - `PriceParser.convert_currency(amount, from_currency, to_currency)` — конвертация по курсу (кэш 6 часов)
    - Поддержка валют: RUB (₽), USD ($), EUR (€), GBP (£), KZT (₸), CNY (¥), TRY (₺)
    - _Требования: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.2 Написать property-тест для round-trip парсинга цен
    - **Свойство 1: Round-trip consistency** — для любого валидного текстового представления цены, `parse(format(parse(text))) == parse(text)`
    - **Проверяет: Требование 3.7**

  - [ ]* 5.3 Написать unit-тесты для PriceParser
    - Тесты парсинга: "1 299,90 ₽" → 1299.90, "$12.99" → 12.99, "12,99 €" → 12.99
    - Тесты форматирования: 1299.90 RUB → "1 299,90 ₽", 12.99 USD → "$12.99"
    - Тесты edge cases: пустая строка, текст без цифр, несколько чисел
    - _Требования: 3.1, 3.2, 3.3, 3.4, 3.6_

- [x] 6. Сервис мониторов (CRUD) и валидация
  - [x] 6.1 Реализовать `app/services/monitor_service.py` — основные CRUD-операции
    - `create_monitor(user_id, data)` — создание монитора с валидацией URL, проверкой дубликатов по нормализованному URL, применением шаблона магазина
    - `get_monitor(user_id, monitor_id)` — получение с проверкой принадлежности пользователю
    - `list_monitors(user_id, filters, pagination)` — список с фильтрацией по тегам, поиску, статусу; пагинация (page, per_page)
    - `update_monitor(user_id, monitor_id, data)` — обновление полей, валидация CSS-селектора и интервала
    - `delete_monitor(user_id, monitor_id)` — каскадное удаление: монитор + price_history + alerts_log + screenshots
    - `toggle_monitor(user_id, monitor_id)` — переключение is_active, при деактивации — удаление из очереди планировщика
    - _Требования: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 6.2 Реализовать валидацию и нормализацию в MonitorService
    - `normalize_url(url)` — lowercase домена, сортировка query params, удаление trailing slash
    - `validate_css_selector(selector)` — валидация через cssselect
    - `validate_check_interval(seconds)` — проверка: 60 <= seconds <= 2592000
    - `check_duplicate(user_id, url)` — проверка дубликата по нормализованному URL, предупреждение пользователю
    - _Требования: 28.1, 28.2, 28.3, 28.4, 28.5_

  - [x] 6.3 Реализовать массовые операции в MonitorService
    - `bulk_operation(user_id, monitor_ids, operation)` — pause, resume, delete, check_now, add_tag
    - _Требования: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 6.4 Написать property-тест для нормализации URL
    - **Свойство 2: URL normalization idempotency** — `normalize_url(normalize_url(url)) == normalize_url(url)`
    - **Проверяет: Требование 28.2**

  - [ ]* 6.5 Написать unit-тесты для MonitorService
    - Тесты CRUD: создание, получение, обновление, удаление
    - Тесты валидации: невалидный URL, невалидный CSS-селектор, интервал вне диапазона
    - Тесты дубликатов: предупреждение при дубликате, создание при подтверждении
    - _Требования: 1.1, 1.2, 1.3, 1.4, 1.5, 28.1, 28.4, 28.5_


- [x] 7. Движок скрапинга
  - [x] 7.1 Реализовать `app/services/scraper_service.py` — ядро скрапинга
    - Класс `ScraperService` с пулом браузеров Playwright (`asyncio.Queue[Browser]`)
    - Пул из 10+ User-Agent строк с ротацией при каждом запросе
    - `scrape(url, config)` — полный цикл: получить браузер из пула → создать контекст (proxy, random UA) → загрузить страницу (timeout 30s) → закрыть cookie-баннеры → выполнить макросы → скриншот → извлечь цену → определить доступность → вернуть браузер
    - `_extract_price(page, config)` — извлечение: CSS-селектор → XPath → JS-выражение → auto-detect (15+ распространённых селекторов цен)
    - `_close_popups(page)` — закрытие cookie-баннеров и всплывающих окон
    - `_retry_with_backoff(func, max_retries=3)` — повторные попытки с экспоненциальной задержкой: 5s, 15s, 45s
    - Обработка HTTP-ошибок: 4xx — без повторов, 5xx — с повторами
    - Поддержка прокси через config
    - _Требования: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [x] 7.2 Реализовать выполнение макросов в ScraperService
    - `_execute_macros(page, steps)` — выполнение шагов: click(selector), type(selector, text), scroll(direction, pixels), wait(seconds), select_option(selector, value), press_key(key)
    - Лимит: до 20 шагов на монитор
    - При ошибке шага — лог с номером шага и типом ошибки, переход к следующему шагу
    - _Требования: 21.1, 21.2, 21.3, 21.4_

  - [ ]* 7.3 Написать unit-тесты для ScraperService
    - Тесты retry с экспоненциальной задержкой
    - Тесты обработки HTTP-ошибок (4xx vs 5xx)
    - Тесты выполнения макросов (порядок, обработка ошибок)
    - _Требования: 2.7, 2.8, 21.4_

- [x] 8. Сервис мониторинга доступности
  - [x] 8.1 Реализовать `app/services/availability_service.py`
    - `check_availability(page, monitor)` — определение статуса доступности по индикаторам: "out of stock", "нет в наличии", "sold out", "распродано", "товар закончился"
    - Поддержка пользовательского CSS-селектора и текстовых паттернов для определения доступности
    - Сохранение availability_status в price_history
    - _Требования: 22.1, 22.4, 22.5_

  - [x] 8.2 Реализовать уведомления об изменении доступности
    - Отправка "Товар снова в наличии!" при переходе out_of_stock → in_stock
    - Отправка "Товар закончился" при переходе in_stock → out_of_stock
    - _Требования: 22.2, 22.3_

- [x] 9. Сервис скриншотов
  - [x] 9.1 Реализовать `app/services/screenshot_service.py`
    - `capture_screenshot(page)` — снимок страницы в JPEG, max width 1280px
    - `save_screenshot(monitor_id, image_data)` — сохранение с привязкой к price_history
    - `rotate_screenshots(monitor_id, max_count=50)` — ротация: удаление старых при превышении лимита
    - `get_screenshots(monitor_id, limit)` — получение скриншотов монитора
    - _Требования: 23.1, 23.2, 23.5, 23.6_

- [ ] 10. Контрольная точка — Ядро системы
  - Убедиться, что скрапинг, парсинг цен, доступность и скриншоты работают корректно. Задать вопросы пользователю при необходимости.

- [x] 11. Система условий и алертов
  - [x] 11.1 Реализовать `app/services/alert_service.py`
    - `evaluate_conditions(monitor, old_price, new_price)` — оценка всех условий: threshold_below, threshold_above, threshold_pct, составные (AND/OR), исторический минимум
    - `check_compound_condition(condition, context)` — рекурсивная оценка составного условия
    - `is_cooldown_active(monitor_id, condition_id)` — проверка cooldown (по умолчанию 1 час)
    - `log_alert(monitor_id, alert_type, message, price)` — запись в alerts_log
    - Проверка исторического минимума — специальное уведомление "Лучшая цена за всё время"
    - _Требования: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 11.2 Написать unit-тесты для AlertService
    - Тесты threshold_below, threshold_above, threshold_pct
    - Тесты составных условий AND/OR
    - Тесты cooldown
    - Тест исторического минимума
    - _Требования: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 12. Сервис уведомлений (мультиканальный)
  - [x] 12.1 Реализовать `app/services/notification_service.py`
    - `send(channels, alert)` — отправка через все активные каналы с retry (3 попытки, 10s задержка)
    - `send_telegram(chat_id, message, screenshot)` — HTML-форматированное сообщение: название товара, старая/новая цена, процент изменения, ссылка + опциональный скриншот
    - `send_email(to, subject, body)` — SMTP отправка через aiosmtplib
    - `send_webhook(url, payload)` — HTTP POST с JSON: monitor_id, name, url, old_price, new_price, change_pct, timestamp
    - `send_discord(webhook_url, message)` — Discord webhook embed
    - `send_slack(webhook_url, message)` — Slack webhook block
    - _Требования: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 12.2 Написать unit-тесты для NotificationService
    - Тесты форматирования Telegram-сообщений
    - Тесты retry при ошибках
    - Тесты формата webhook payload
    - _Требования: 5.3, 5.4, 5.5_


- [x] 13. Планировщик проверок
  - [x] 13.1 Реализовать `app/services/scheduler_service.py`
    - Класс `SchedulerService` с `asyncio.PriorityQueue` (next_run_time, monitor_id), worker pool, `asyncio.Semaphore(max_concurrent=5)`
    - `start()` — загрузить все активные мониторы, распределить проверки равномерно (jitter), запустить workers
    - `schedule_monitor(monitor_id, interval)` — добавить/обновить расписание
    - `unschedule_monitor(monitor_id)` — удалить из расписания при деактивации/удалении
    - `enqueue_immediate(monitor_ids)` — немедленная проверка в очередь
    - `_worker()` — loop: dequeue → scrape → save price_history → update monitor (last_price, last_checked) → evaluate alerts → send notifications
    - `_distribute_evenly(monitors)` — распределение начальных проверок равномерно по интервалу
    - Ограничение: не более 5 параллельных проверок при очереди > 100
    - _Требования: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 13.2 Интегрировать планировщик с обработкой ошибок мониторов
    - Инкремент `consecutive_failures` при неудачной проверке
    - Уведомление "Монитор не работает" после 3 последовательных неудач
    - Уведомление "Монитор восстановлен" при успешной проверке после серии неудач
    - Автоматическая приостановка монитора (is_active=false) после 24 часов в состоянии ошибки
    - Сброс consecutive_failures при успешной проверке
    - _Требования: 26.1, 26.2, 26.3, 26.5_

  - [ ]* 13.3 Написать unit-тесты для SchedulerService
    - Тесты равномерного распределения проверок
    - Тесты ограничения параллелизма
    - Тесты обработки consecutive_failures
    - _Требования: 6.5, 6.6, 26.1, 26.3_

- [x] 14. Сервис кэширования
  - [x] 14.1 Реализовать `app/services/cache_service.py`
    - TTL-кэш на основе cachetools (TTLCache)
    - Кэширование: список мониторов, статистика — TTL 60 секунд
    - Инвалидация кэша при изменении данных
    - _Требования: 27.6_

- [ ] 15. Контрольная точка — Бэкенд-сервисы
  - Убедиться, что планировщик, алерты, уведомления и кэш работают корректно. Задать вопросы пользователю при необходимости.

- [x] 16. REST API v1
  - [x] 16.1 Реализовать `app/api/deps.py` — зависимости API
    - `get_current_user()` — аутентификация по JWT или API-ключу из заголовка Authorization
    - `get_pagination()` — параметры пагинации: page (default 1), per_page (default 20, max 100)
    - Rate limiter: sliding window counter, 100 запросов/мин на API-ключ, HTTP 429 с Retry-After
    - _Требования: 10.2, 10.3, 10.4, 27.1, 27.2_

  - [x] 16.2 Реализовать `app/api/router.py` и `app/api/monitors.py` — CRUD мониторов
    - Главный роутер `/api/v1` с CORS middleware (настраиваемый список origins)
    - GET /api/v1/monitors — список с пагинацией, фильтрами (tag, search, status)
    - POST /api/v1/monitors — создание монитора, HTTP 201
    - GET /api/v1/monitors/{id} — детали
    - PUT /api/v1/monitors/{id} — обновление
    - DELETE /api/v1/monitors/{id} — удаление
    - POST /api/v1/monitors/{id}/check — немедленная проверка
    - Формат ответа: `{"data": ..., "error": null, "meta": {"total", "page", "per_page", "total_pages"}}`
    - Формат ошибки: `{"data": null, "error": "описание", "meta": null}`
    - _Требования: 10.1, 10.5, 10.7, 19.2, 19.4, 19.5_

  - [x] 16.3 Реализовать `app/api/history.py` — история цен и графики
    - GET /api/v1/monitors/{id}/history — записи price_history с параметрами days, limit
    - GET /api/v1/monitors/{id}/chart — данные для графика: массив (timestamp, price)
    - GET /api/v1/monitors/{id}/screenshots — скриншоты монитора
    - _Требования: 10.1, 10.6, 11.4_

  - [x] 16.4 Реализовать `app/api/alerts.py` — алерты и условия
    - GET /api/v1/alerts — лог алертов с пагинацией и фильтрами (monitor_id, alert_type, period)
    - GET /api/v1/alerts/conditions/{monitor_id} — условия алертов монитора
    - POST /api/v1/alerts/conditions — создание условия алерта
    - _Требования: 10.1_

  - [x] 16.5 Реализовать `app/api/groups.py` — группы сравнения
    - CRUD: GET/POST /api/v1/groups, GET/PUT/DELETE /api/v1/groups/{id}
    - GET /api/v1/groups/{id} — детали группы с текущими ценами, сортировка по цене
    - _Требования: 12.1, 12.2, 12.4_

  - [x] 16.6 Реализовать `app/api/tags.py` — теги
    - GET /api/v1/tags — список тегов пользователя
    - POST /api/v1/tags — создание тега
    - DELETE /api/v1/tags/{id} — удаление тега (с удалением связей)
    - _Требования: 13.1, 13.2, 13.3, 13.4_

  - [x] 16.7 Реализовать `app/api/export.py` — импорт/экспорт
    - GET /api/v1/export/json — экспорт всех мониторов с настройками, тегами, историей
    - GET /api/v1/export/csv — CSV: monitor_name, url, current_price, min_price, max_price, avg_price, currency, tags, created_at
    - POST /api/v1/import/json — валидация + импорт, отчёт: imported, skipped, errors
    - _Требования: 14.1, 14.2, 14.3, 14.4_

  - [x] 16.8 Реализовать `app/api/bulk.py` — массовые операции
    - POST /api/v1/monitors/bulk — операции: pause, resume, delete, check_now, add_tag
    - _Требования: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 16.9 Реализовать `app/api/templates.py` — шаблоны мониторов
    - GET /api/v1/templates — список шаблонов
    - POST /api/v1/templates — создание пользовательского шаблона
    - _Требования: 25.3, 25.5_

  - [x] 16.10 Реализовать `app/api/settings.py` и `app/api/health.py`
    - GET/PUT /api/v1/settings — настройки пользователя (timezone, quiet_hours, digest, default_interval)
    - GET /api/v1/stats — общая статистика (количество мониторов, активных, точек данных, алертов)
    - GET /health — статус компонентов: БД, Playwright, Планировщик, Telegram-бот
    - _Требования: 17.3, 17.5, 24.5_

  - [x] 16.11 Реализовать обработку ошибок API
    - Структурированные JSON-ответы: error + detail, HTTP-коды 400/401/403/404/429/500
    - Не раскрывать внутренние детали реализации
    - HTTP 401 при отсутствии валидного API-ключа
    - HTTP 403 при попытке доступа к чужим ресурсам
    - _Требования: 20.4, 10.2, 16.4_

  - [ ]* 16.12 Написать property-тест для round-trip экспорта/импорта
    - **Свойство 3: Export/Import round-trip** — для любого валидного набора мониторов, `import(export(monitors))` создаёт мониторы с эквивалентными настройками
    - **Проверяет: Требование 14.6**

  - [ ]* 16.13 Написать unit-тесты для REST API
    - Тесты CRUD мониторов через API
    - Тесты пагинации и фильтрации
    - Тесты аутентификации (401, 403)
    - Тесты rate limiting (429)
    - _Требования: 10.1, 10.2, 10.4, 27.1, 27.2_


- [ ] 17. Контрольная точка — REST API
  - Убедиться, что все API-эндпоинты работают, аутентификация, пагинация и rate limiting функционируют. Задать вопросы пользователю при необходимости.

- [x] 18. Сервисы сравнения, экспорта, шаблонов и дайджестов
  - [x] 18.1 Реализовать `app/services/comparison_service.py`
    - `create_group(user_id, name, monitor_ids)` — создание группы сравнения
    - `get_group(user_id, group_id)` — список мониторов с ценами, сортировка по цене (мин → макс)
    - `update_group(user_id, group_id, data)` — добавление/удаление мониторов
    - `delete_group(user_id, group_id)` — удаление группы без удаления мониторов
    - Уведомление "Лучшая цена в группе" при изменении минимальной цены
    - _Требования: 12.1, 12.2, 12.3, 12.4_

  - [x] 18.2 Реализовать `app/services/export_service.py`
    - `export_json(user_id)` — полный экспорт: мониторы, настройки, теги, история цен
    - `export_csv(user_id)` — CSV с колонками: monitor_name, url, current_price, min_price, max_price, avg_price, currency, tags, created_at
    - `import_json(user_id, data)` — валидация структуры, создание мониторов, отчёт (imported, skipped, errors)
    - _Требования: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 18.3 Реализовать `app/services/template_service.py`
    - `get_template_for_url(url)` — определение шаблона по домену URL
    - `apply_template(monitor, template)` — применение селектора, валюты, паттернов доступности
    - `seed_templates()` — заполнение 15+ шаблонов: Ozon, Wildberries, Яндекс.Маркет, DNS, М.Видео, Ситилинк, AliExpress, Amazon, eBay, ASOS, Lamoda, Avito, IKEA, Leroy Merlin, Citilink
    - Fallback: если селектор шаблона не находит элемент — автоматическое определение цены
    - _Требования: 25.1, 25.2, 25.4, 25.5_

  - [x] 18.4 Реализовать `app/services/digest_service.py`
    - `check_quiet_hours(user_id)` — проверка тихих часов с учётом часового пояса пользователя
    - `queue_alert(user_id, alert)` — постановка алерта в очередь (таблица queued_alerts)
    - `send_queued_alerts(user_id)` — отправка накопленных алертов одним дайджест-сообщением
    - `generate_daily_digest(user_id)` — все изменения цен за 24 часа
    - `generate_weekly_digest(user_id)` — тренды, лучшие предложения за неделю
    - Интеграция с планировщиком: запуск дайджестов по расписанию пользователя
    - _Требования: 24.1, 24.2, 24.3, 24.4, 24.5_

  - [ ]* 18.5 Написать unit-тесты для сервисов сравнения, экспорта, шаблонов
    - Тесты группы сравнения: создание, сортировка по цене, уведомление о лучшей цене
    - Тесты экспорта/импорта: JSON, CSV, обработка невалидных записей
    - Тесты шаблонов: определение по домену, fallback
    - _Требования: 12.2, 12.3, 14.3, 14.4, 25.2, 25.4_

- [x] 19. Telegram-бот
  - [x] 19.1 Реализовать `app/bot/handlers.py` — основные команды
    - `/start` — приветствие, создание пользователя через AuthService
    - `/add` — запуск ConversationHandler: название → URL → селектор (/skip) → пороги (/skip) → подтверждение
    - `/list` — список мониторов с inline-клавиатурой (пауза/возобновление, удаление), пагинация по 10 с кнопками "Далее"/"Назад"
    - `/check` — немедленная проверка всех активных мониторов, отображение результатов
    - `/edit_{id}` — диалог редактирования монитора
    - `/report` — сводный отчёт за 24 часа: изменения цен, сработавшие алерты
    - `/stats` — общая статистика
    - `/settings` — настройки с inline-клавиатурой (интервал, каналы, часовой пояс)
    - `/export` — отправка JSON-файла с экспортом мониторов
    - `/apikey` — генерация API-ключа, отправка в личном сообщении
    - `/digest` — немедленный дайджест
    - `/compare_{group_id}` — сравнительная таблица группы
    - `/help` — справка по командам
    - Отправка URL без команды → предложение создать монитор с автоопределением цены и названия
    - _Требования: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.9, 7.10_

  - [x] 19.2 Реализовать `app/bot/conversations.py` — ConversationHandler flows
    - Пошаговый диалог добавления монитора с состояниями
    - Пошаговый диалог редактирования монитора
    - Обработка /skip для опциональных полей
    - _Требования: 7.1, 7.5_

  - [x] 19.3 Реализовать `app/bot/callbacks.py` — inline keyboard callbacks
    - Обработка нажатий inline-кнопок: пауза/возобновление, удаление, пагинация
    - Обновление сообщения с актуальным состоянием в течение 3 секунд
    - Индикатор ошибки (⚠️) для мониторов с consecutive_failures > 0
    - _Требования: 7.8, 26.6_

  - [x] 19.4 Реализовать `app/bot/formatters.py` и `app/bot/keyboards.py`
    - Форматирование сообщений: HTML-разметка, эмодзи, таблицы сравнения
    - Построение inline-клавиатур: действия монитора, пагинация, настройки
    - Парсинг макросов из текстового формата: "click .btn-price; wait 2; scroll down 500"
    - _Требования: 7.2, 7.7, 7.8, 21.6, 24.6_

  - [ ]* 19.5 Написать unit-тесты для Telegram-бота
    - Тесты форматирования сообщений
    - Тесты парсинга макросов из текстового формата
    - Тесты построения inline-клавиатур
    - _Требования: 7.1, 7.2, 21.6_


- [ ] 20. Контрольная точка — Telegram-бот и сервисы
  - Убедиться, что все команды бота работают, inline-клавиатуры функционируют, дайджесты и шаблоны корректны. Задать вопросы пользователю при необходимости.

- [x] 21. Веб-дашборд — HTML-шаблоны и маршруты
  - [x] 21.1 Реализовать `app/web/routes.py` — маршруты веб-дашборда
    - Главная страница `/` — список мониторов, статистика (общее количество, активные, с ценой, точки данных), форма добавления монитора
    - Страница детализации `/monitor/{id}` — график цен (Chart.js), переключатели периодов (7д, 30д, 90д, 1г, всё), статистика (мин/макс/средняя/медиана), таблица истории, скриншоты
    - Страница алертов `/alerts` — история алертов с фильтрацией по монитору, типу, периоду
    - Страница настроек `/settings` — настройки пользователя
    - Страница логина `/login` — аутентификация через API-ключ или Telegram OAuth
    - _Требования: 8.1, 8.2, 8.3, 8.7, 8.8_

  - [x] 21.2 Реализовать `app/web/auth.py` — веб-аутентификация
    - Сессионная аутентификация на основе JWT-токена
    - Middleware для проверки авторизации на защищённых страницах
    - _Требования: 16.5_

  - [x] 21.3 Создать Jinja2-шаблоны с тёмной темой
    - `templates/base.html` — базовый шаблон с тёмной темой: фон #0a0a0f, карточки #1a1a2e, акцент #6c5ce7, зелёный #00b894, красный #e17055
    - `templates/dashboard.html` — главная: список мониторов с бейджами доступности, статистика, форма добавления, фильтрация по тегам/поиску без перезагрузки
    - `templates/detail.html` — детализация: Chart.js график, переключатели периодов, статистика, таблица истории, скриншоты
    - `templates/alerts.html` — история алертов с фильтрами
    - `templates/settings.html` — настройки пользователя
    - `templates/login.html` — страница входа
    - _Требования: 8.1, 8.2, 8.4, 8.6, 8.7, 8.8, 22.6, 23.4, 26.4_

  - [x] 21.4 Создать `static/style.css` — стили тёмной темы
    - Адаптивный дизайн: 320px — 2560px
    - Цветовая схема: фон #0a0a0f, карточки #1a1a2e, акцент #6c5ce7, зелёный #00b894, красный #e17055
    - Стили для карточек мониторов, графиков, таблиц, форм, бейджей
    - Бесконечная прокрутка или пагинация для списка мониторов
    - _Требования: 8.4, 8.6, 27.4_

- [x] 22. Визуальный селектор элементов
  - [x] 22.1 Реализовать `app/services/visual_selector_service.py`
    - `proxy_page(url)` — загрузка страницы через Playwright, получение rendered HTML, переписывание относительных URL на абсолютные, инжекция JS для перехвата кликов
    - `generate_css_selector(element_path)` — генерация уникального CSS-селектора
    - `generate_xpath(element_path)` — генерация XPath-выражения
    - _Требования: 9.1, 9.2, 9.3_

  - [x] 22.2 Реализовать `app/web/visual_selector.py` — маршруты визуального селектора
    - Эндпоинт для проксирования страницы
    - Эндпоинт для генерации селектора по клику
    - _Требования: 9.1, 9.6_

  - [x] 22.3 Создать `templates/visual_selector.html` и `static/js/visual-selector.js`
    - iframe-превью с загруженной страницей
    - Перехват кликов: подсветка элемента рамкой, отображение панели с CSS-селектором, XPath, текстом, распознанной ценой
    - Кнопки "Расширить выделение" (родительский элемент) и "Сузить выделение" (первый дочерний)
    - Кнопка подтверждения выбора → сохранение селектора в монитор
    - _Требования: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 23. Конструктор макросов (веб-интерфейс)
  - [x] 23.1 Создать `templates/macro_builder.html` и `static/js/macro-builder.js`
    - Конструктор макросов: добавление, удаление, drag-and-drop для изменения порядка шагов
    - Типы шагов: click, type, scroll, wait, select_option, press_key
    - Для каждого шага: выбор типа, ввод селектора, параметры
    - Сохранение макроса через API
    - _Требования: 21.5_

- [ ] 24. Контрольная точка — Веб-дашборд и визуальный селектор
  - Убедиться, что веб-дашборд отображается корректно, визуальный селектор работает, конструктор макросов функционирует. Задать вопросы пользователю при необходимости.


- [x] 25. Логирование и мониторинг системы
  - [x] 25.1 Реализовать структурированное логирование
    - Настроить logging с форматом: timestamp, уровень (INFO/WARNING/ERROR/CRITICAL), компонент, сообщение, контекст (monitor_id, user_id)
    - Логирование ошибок проверки: URL, тип ошибки, текст, номер попытки, длительность
    - CRITICAL-лог при переходе компонента в нерабочее состояние + уведомление администратору через Telegram
    - Метрики: количество проверок/мин, среднее время проверки, количество ошибок, количество алертов
    - _Требования: 17.1, 17.2, 17.4, 17.5_

- [x] 26. Обработка ошибок и отказоустойчивость
  - [x] 26.1 Реализовать обработку ошибок во всех компонентах
    - Reconnect к БД: до 5 попыток с экспоненциальной задержкой (уже в database.py, интегрировать во все сервисы)
    - Playwright recovery: завершение зависшего браузера, запуск нового экземпляра, повтор проверки
    - Telegram API 429: приостановка отправки на время Retry-After
    - Connection pooling: max_size=20 (уже в database.py)
    - _Требования: 20.1, 20.2, 20.3, 20.5_

- [x] 27. История цен и аналитика
  - [x] 27.1 Реализовать аналитику в MonitorService / отдельном сервисе
    - Запись price_history при каждой успешной проверке: price, raw_text, availability_status, screenshot_id, recorded_at
    - Вычисление статистики: min, max, avg, median, count, дата лучшей цены
    - Флаг "Лучшая цена за всё время" при текущей цене = историческому минимуму
    - Данные для графика: массив (timestamp, price) за период
    - Хранение без ограничения по времени, удаление только при удалении монитора
    - _Требования: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 28. Развёртывание и инфраструктура
  - [x] 28.1 Создать/обновить `Dockerfile`
    - Один контейнер: FastAPI + Telegram-бот + Планировщик + Playwright
    - Установка Playwright browsers в Docker
    - Healthcheck на /health
    - _Требования: 18.1, 18.4_

  - [x] 28.2 Создать/обновить `docker-compose.yml`
    - Сервис app + PostgreSQL
    - Переменные окружения из .env
    - _Требования: 18.1_

  - [x] 28.3 Создать/обновить `railway.toml`
    - Конфигурация для Railway: healthcheck /health, автоматический перезапуск
    - _Требования: 18.4_

  - [x] 28.4 Реализовать `app/main.py` — точка входа
    - Инициализация FastAPI с CORS middleware
    - Подключение роутеров: API v1, web routes, health
    - Запуск Telegram-бота (polling/webhook)
    - Запуск планировщика
    - Запуск миграций БД при старте
    - Lifespan: startup (init DB, browser pool, scheduler) / shutdown (cleanup)
    - _Требования: 18.1, 18.5, 19.1, 19.3, 19.4, 19.5_

- [ ] 29. Контрольная точка — Полная интеграция
  - Убедиться, что все компоненты работают вместе: API, бот, дашборд, планировщик, уведомления. Docker-контейнер собирается и запускается. Задать вопросы пользователю при необходимости.

- [x] 30. Финальная интеграция и связывание компонентов
  - [x] 30.1 Связать планировщик с полным pipeline проверки
    - Worker: dequeue → load monitor config → scrape (с макросами) → parse price → check availability → save screenshot → save price_history → update monitor → evaluate alerts → check quiet hours → send/queue notifications → log
    - Интеграция всех сервисов в единый pipeline
    - _Требования: 1.1, 2.1, 3.1, 4.1, 5.2, 6.2, 22.5, 23.1, 24.1_

  - [x] 30.2 Связать Telegram-бот с сервисным слоем
    - Все команды бота вызывают методы сервисного слоя (не прямые SQL-запросы)
    - Единый источник бизнес-логики для API, бота и дашборда
    - _Требования: 19.2_

  - [x] 30.3 Связать веб-дашборд с API
    - Все данные на дашборде загружаются через REST API (fetch)
    - Фильтрация и пагинация без перезагрузки страницы
    - Обновление графиков при смене периода через API
    - _Требования: 8.3, 8.7, 19.2_

  - [ ]* 30.4 Написать интеграционные тесты
    - Тест полного pipeline: создание монитора → проверка → алерт → уведомление
    - Тест API: CRUD через HTTP-запросы
    - Тест пагинации с большим количеством мониторов
    - _Требования: 1.1, 4.1, 5.2, 27.1_

- [ ] 31. Финальная контрольная точка
  - Убедиться, что все тесты проходят, все 28 требований покрыты реализацией. Задать вопросы пользователю при необходимости.

## Примечания

- Задачи с `*` — опциональные (тесты), можно пропустить для быстрого MVP
- Каждая задача ссылается на конкретные требования для трассируемости
- Контрольные точки обеспечивают инкрементальную валидацию
- Property-тесты проверяют универсальные свойства корректности (round-trip)
- Unit-тесты проверяют конкретные примеры и edge cases
- Все сервисы используют async/await для совместимости с единым event loop
