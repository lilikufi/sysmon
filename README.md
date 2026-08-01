# Sysmon

Внутреннее Django-приложение для инвентаризации и мониторинга узлов сети. Основной
интерфейс находится в приложении `hosting`; терминал по WebSocket работает через
Django Channels.

## Локальный запуск

Требуется Python 3.12.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements\dev.txt
Copy-Item .env.example .env
python itproger\manage.py migrate
python -m uvicorn itproger.asgi:application --app-dir itproger --reload
```

### Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
cp .env.example .env
python itproger/manage.py migrate
python -m uvicorn itproger.asgi:application --app-dir itproger --reload
```

Приложение будет доступно по адресу <http://127.0.0.1:8000/>. Настройки читаются
из файла `.env` в корне репозитория и могут быть переопределены переменными процесса.

## Проверки

```powershell
python itproger\manage.py check
python itproger\manage.py makemigrations --check --dry-run
python itproger\manage.py test accounts hosting
ruff check itproger
```

Эти же команды выполняются в GitHub Actions.

## Конфигурация

Обязательные production-параметры:

- `DJANGO_SECRET_KEY` — случайный секрет Django;
- `DJANGO_DEBUG=false`;
- `DJANGO_ALLOWED_HOSTS` — список имён и адресов через запятую;
- `NAG_SERVER`, `NAG_USERNAME`, `NAG_PASSWORD` — доступ к серверу мониторинга.

Встроенный планировщик отключён по умолчанию, чтобы он не запускался внутри
миграций, тестов и каждого web-worker. Для совместимого одиночного развёртывания
его можно временно включить через `SYSMON_ENABLE_SCHEDULER=true`.

LDAP отключён по умолчанию. Для него установите `requirements/ldap.txt`, задайте
LDAP-параметры развёртывания и включите `DJANGO_ENABLE_LDAP=true`.

## Данные и артефакты

`db.sqlite3`, `uploads/`, `staticfiles/` и логи являются runtime-данными и не должны
добавляться в новые коммиты. Уже отслеживаемые копии пока оставлены на месте, чтобы
уборка репозитория не уничтожила рабочие данные.

Статика для развёртывания собирается командой:

```powershell
python itproger\manage.py collectstatic --noinput
```

Локальную базу перед созданием скриншотов или демонстрацией можно обезличить:

```powershell
python itproger\manage.py anonymize_demo_data
```

Команда заменяет логины, имена, названия хостов и IP-адреса, очищает email и сохраняет пароли,
права пользователей, связи между моделями и позиции устройств на графе. После запуска
логин суперпользователя — `admin01`. Для воспроизводимого набора данных можно добавить
параметр `--seed`, например `--seed 20260731`. Перед запуском на нужной локальной базе
следует создать её резервную копию.

## Структура

- `itproger/itproger/` — настройки Django и ASGI;
- `itproger/hosting/` — узлы сети, сервисы, карта и SSH WebSocket;
- `itproger/accounts/` — вход, выход и смена пароля;
- `itproger/stream/` — фоновые проверки и интеграционные скрипты;
- `itproger/news/` — модуль новостей, сейчас не подключён к корневым URL;
