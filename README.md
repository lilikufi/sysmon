# Sysmon

Django-приложение для инвентаризации и мониторинга сетевых узлов. В проект входят
веб-интерфейс, карта сети, фоновые проверки и SSH-терминал через Django Channels.

## Быстрый запуск в Windows

Требуется Python 3.12.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements\dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe itproger\manage.py migrate
.\.venv\Scripts\python.exe -m uvicorn itproger.asgi:application --app-dir itproger --reload
```

Откройте <http://127.0.0.1:8000/>. Активация виртуального окружения не требуется.

## Запуск в Linux и macOS

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements/dev.txt
cp .env.example .env
.venv/bin/python itproger/manage.py migrate
.venv/bin/python -m uvicorn itproger.asgi:application --app-dir itproger --reload
```

### Демонстрационные хосты и сервисы

Репозиторий не содержит локальную SQLite-базу. Чтобы наполнить чистую базу
обезличенными демонстрационными данными, после применения миграций выполните:

```bash
.venv/bin/python itproger/manage.py loaddata demo_hosts
```

Fixture добавляет категории, 167 хостов и 68 сервисов. Пользователи, сессии,
журналы, маршруты и позиции карты в него не входят.

## Настройка

Локальные параметры хранятся в `.env`. Начальный шаблон находится в
`.env.example`. Не добавляйте `.env`, базы данных, пользовательские загрузки,
логи и SSH-ключи в Git.

Основные переменные:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` — настройки Django;
- `NAG_SERVER`, `NAG_USERNAME`, `NAG_PASSWORD` — подключение к серверу мониторинга;
- `SYSMON_SNMP_COMMUNITIES` — SNMP community strings через запятую;
- `SYSMON_MAIL_*` — параметры почтовых уведомлений;
- `SYSMON_ENABLE_SCHEDULER` — включение встроенного планировщика;
- `DJANGO_ENABLE_LDAP` — включение LDAP после установки `requirements/ldap.txt`.

## Проверки

```powershell
.\.venv\Scripts\python.exe itproger\manage.py check
.\.venv\Scripts\python.exe itproger\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe itproger\manage.py test accounts hosting
.\.venv\Scripts\python.exe -m ruff check itproger
```

## Служебные команды

Сборка статики:

```powershell
.\.venv\Scripts\python.exe itproger\manage.py collectstatic --noinput
```

Обезличивание локальной демонстрационной базы:

```powershell
.\.venv\Scripts\python.exe itproger\manage.py anonymize_demo_data
```

Перед обезличиванием создайте резервную копию базы.

## Структура проекта

- `itproger/itproger/` — настройки Django и ASGI;
- `itproger/hosting/` — сетевые узлы, сервисы, карта и SSH-терминал;
- `itproger/accounts/` — аутентификация пользователей;
- `itproger/stream/` — фоновые проверки и интеграции;
- `requirements/` — зависимости для разных вариантов установки.
