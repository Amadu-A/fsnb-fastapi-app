
# fsnb-fastapi — базовый каркас веб‑приложения на FastAPI

Лёгкий, но «живой» стартовый проект: веб‑шаблоны (Jinja2), сессии и формы, JWT‑авторизация для API, пользователи/профили/права, загрузка аватара, а также простая админ‑панель с регистрацией моделей «как в Django». Стек — **FastAPI + SQLAlchemy (async) + Alembic + Jinja2 + OAuth2/JWT**.

---

## Содержание

- [Возможности](#возможности)
- [Архитектура и стек](#архитектура-и-стек)
- [Структура проекта](#структура-проекта)
- [Быстрый старт](#быстрый-старт)
  - [Требования](#требования)
  - [Переменные окружения](#переменные-окружения)
  - [Инициализация БД](#инициализация-бд)
  - [Запуск dev‑сервера](#запуск-dev-сервера)
  - [Создание суперпользователя](#создание-суперпользователя)
- [Веб‑интерфейс](#веб-интерфейс)
  - [/ – главная](#--главная)
  - [/login, /register – вход/регистрация](#login-register--входрегистрация)
  - [/profile – профиль и аватар](#profile--профиль-и-аватар)
  - [/admin – админ‑панель](#admin--админ-панель)
- [API (OAuth2/JWT)](#api-oauth2jwt)
  - [/api/v1/auth/token](#apiv1authtoken)
  - [/api/v1/users](#apiv1users)
- [Модели и права](#модели-и-права)
- [Регистрация моделей в админке (аналог django admin.py)](#регистрация-моделей-в-админке-аналог-django-adminpy)
- [Загрузка файлов и ограничения](#загрузка-файлов-и-ограничения)
- [Расширение и доработка](#расширение-и-доработка)
- [Подсказки и устранение проблем](#подсказки-и-устранение-проблем)

---

## Возможности

- Пользователи с профилем и правами (**User ↔ Profile ↔ Permission**).
- Авторизация:
  - веб‑часть — через **сессии и формы**;
  - API — через **OAuth2 Password** и **JWT**.
- Профиль пользователя: редактирование полей + **загрузка/предпросмотр аватара** (кнопка «Удалить» и дефолтная картинка).
- Ограничения на файл аватара: **только изображения**, **≤ 3 МБ**, **минимум 40×40 px**; при замене старый файл удаляется.
- Простая **админ‑панель**:
  - вход только для `is_superadmin` или `is_admin`;
  - список зарегистрированных моделей, просмотр/редактирование полей с ограничениями read‑only;
  - управление правами пользователей (админ не может менять флаги супер‑админа).
- «Django‑like» **регистрация моделей** для админки в `base_app/admin.py` (аналог `admin.site.register()`).

---

## Архитектура и стек

- **FastAPI** (асинхронный веб‑фреймворк).
- **SQLAlchemy (async)** + **Alembic** (ORM и миграции).
- **Jinja2** (шаблоны), **Starlette sessions** (сессии).
- **Passlib (bcrypt_sha256)** для хеширования паролей.
- **python-jose** для JWT.
- **Poetry** для зависимостей (см. `pyproject.toml`).

Отдельная настройка: `base_app/core/config.py` — Pydantic Settings с префиксом переменных окружения `APP_CONFIG__…`.

---

## Структура проекта

Главные узлы (примерно):

```
FastAPIbase/
├─ src/
│  ├─ main.py
│  ├─ manage.py               # CLI (create_superuser и пр.)
│  ├─ admin.py                # реестр моделей для админки
│  ├─ logging.py
│  ├─ core/
│  │  ├─ views/
│  │  │  ├─ web.py
│  │  │  ├─ auth.py
│  │  │  └─ admin.py          # (или admin_views.py)
│  │  ├─ api/
│  │  │  └─ api_v1/
│  │  │     ├─ __init__.py    # сборка роутеров v1
│  │  │     ├─ users.py
│  │  │     └─ auth.py
│  │  ├─ models/
│  │  │  ├─ __init__.py
│  │  │  ├─ base.py
│  │  │  ├─ db_helper.py
│  │  │  ├─ permission.py
│  │  │  ├─ profile.py
│  │  │  └─ user.py
│  │  ├─ schemas/
│  │  │  ├─ __init__.py
│  │  │  ├─ permission.py
│  │  │  ├─ profile.py
│  │  │  └─ user.py
│  │  ├─ services/
│  │  │  ├─ __init__.py
│  │  │  └─ auth_service.py
│  │  ├─ mailing/
│  │  │  ├─ __init__.py
│  │  │  └─ mail.py
│  │  ├─ utils/
│  │  │  ├─ __init__.py
│  │  │  └─ case_converter.py
│  │  ├─ config.py
│  │  ├─ email_tokens.py
│  │  ├─ security.py
│  │  └─ dependencies.py      # DI-провайдеры (возвращают crud)
│  ├─ crud/
│  │  ├─ user_repository.py
│  │  ├─ profile_repository.py
│  │  └─ permission_repository.py
│  ├─ templates/
│  │  ├─ core/{base,_header,login,register,profile,index}.html
│  │  ├─ users/list.html
│  │  └─ admin/{index,login,users,user_edit,profile_edit,perm_edit,model_list,model_edit}.html
│  └─ scripts/
│     └─ superuser.py
├─ static/
│  ├─ css/style.css
│  ├─ js/{app.js,avatar-preview.js}
│  ├─ img/
│  └─ uploads/avatars/
├─ alembic/
│  ├─ env.py
│  └─ versions/*.py
├─ docker-compose.yml
├─ poetry.lock
├─ Readme.md
├─ alembic.ini
├─ .gitignore
├─ .env
├─ .env.example
└─ pyproject.toml
```

---

## Быстрый старт

### Требования

- Python 3.12+
- PostgreSQL 14+ (или совместимый)
- Poetry

### Переменные окружения

Конфиг читается через Pydantic Settings с префиксом `APP_CONFIG__` и разделителем `__` (см. `base_app/core/config.py`). Обязательное:

```bash
APP_CONFIG__DB__URL=postgresql+asyncpg://user:password@localhost:5432/dbname
```

Рекомендуется задать секреты:

```bash
APP_CONFIG__AUTH__SECRET_KEY=change_me
APP_CONFIG__AUTH__EMAIL_VERIFY_SECRET=change_me_too
```

> В корне используйте корректный `.env` или `.env.example` (проверьте отсутствие опечаток в имени файла).


## Start project services with Compose

From the project root (where `docker-compose.yml` lives):

```bash
# Launch in background
docker compose up -d
# See container status
docker compose ps
# Stream logs (select services as needed)
docker compose logs -f postgres adminer mail
```
## Services & default addresses

Below are the **typical** defaults used in this project. If you changed ports or service names in `docker-compose.yml`, adjust accordingly.

### PostgreSQL (DB)

- **Internal service name (Compose network):** `postgres` (sometimes `db`)  
- **Internal port:** `5432`  
- **Published host port (example):** `5436`  
- **Default credentials (match your app’s DSN):**
  - **DB name:** `shop`
  - **User:** `user`
  - **Password:** `password`

#### Connect from your host (psql / GUI):
```bash
psql "postgresql://user:password@localhost:5436/shop"
```
### Adminer (DB UI)

- **URL (browser):** http://localhost:8091

At the login screen choose:

| Field    | Value (inside Docker network)  | Alternative (through host port map) |
|----------|--------------------------------|--------------------------------------|
| System   | PostgreSQL                     | PostgreSQL                           |
| Server   | `postgres`  *(or `db`)*        | `host.docker.internal:5436` *(Linux may use `172.17.0.1:5436`)* |
| Username | `user`                         | `user`                               |
| Password | `password`                     | `password`                           |
| Database | `shop`                         | `shop`                               |

> **Tip:** If Adminer can’t connect using `postgres` (or `db`), check the actual service name in `docker-compose.yml`.  
> When using the **host port** variant, make sure Postgres is published on that port (e.g., `5436:5432`).


### Инициализация БД

```bash
poetry install
poetry run alembic upgrade head
```

Миграции находятся в `alembic/versions` и создают таблицы `users`, `profiles`, `permissions` с каскадными связями и триггером удаления.

### Запуск dev‑сервера

```bash
poetry run python -m base_app.main
# или:
# poetry run uvicorn base_app.main:app --reload --port 8015
```

Параметры хоста/порта берутся из `base_app/core/config.py` (`run.host`, `run.port`).

### Создание суперпользователя

Есть два пути:

1) **CLI-обёртка**:

```bash
poetry run python -m base_app.manage --create_superuser
```

Скрипт интерактивно спросит `username`, `password`, `email` и выставит ключевые флаги прав (is_superadmin/is_admin и т. п.).

2) **Прямая утилита**:

```bash
poetry run python -m base_app.scripts.superuser
```

---

## Веб‑интерфейс

### `/` — главная

Базовая страница на Jinja2 (`templates/core/index.html`). Шапка из `_header.html` показывает «Профиль/Выйти» для авторизованных, «Вход/Регистрация» — для гостя.

### `/login`, `/register` — вход/регистрация

Формы находятся в `templates/core/{login,register}.html`, обработчики — `base_app/views/auth.py`. После входа создаётся сессионная авторизация для веб‑части.

### `/profile` — профиль и аватар

- Шаблон: `templates/core/profile.html`.
- JS‑предпросмотр: `static/js/avatar-preview.js` (подключается через `base.html` с `defer`).
- Серверная валидация:
  - только **image/***;
  - размер файла ≤ **3 МБ**;
  - **минимум 40×40 px** (иначе будет alert/ошибка);
  - при загрузке **старый аватар удаляется** (не копим мусор).
- Хранение: `static/uploads/avatars/`; кнопка «Удалить аватар» — под мини‑превью справа от заголовка «Профиль».

Поля профиля: `nickname`, `first_name`, `second_name`, `phone`, `email`, `tg_id`, `tg_nickname`, `session`, `verification` и др.

### `/admin` — админ‑панель

- Вход по `/admin/login` (CSRF в форме), хранится отдельная админ‑сессия.
- Допускаются пользователи, у кого в связанной записи `Permission` стоит `is_superadmin=True` **или** `is_admin=True`.
- Индекс показывает доступные модели (из реестра): `Users`, `Profiles`, `Permissions`.
- Список/редактирование:
  - списки: `templates/admin/users.html`, `model_list.html`;
  - редактирование: `templates/admin/{user_edit,profile_edit,perm_edit,model_edit}.html`.
- Логика прав:
  - супер‑админ может менять всем всё;
  - обычный админ **не может** изменять флаги супер‑админа;
  - `is_superadmin` виден всем, но менять его может только супер‑админ.

---

## API (OAuth2/JWT)

### `/api/v1/auth/token`

`POST x-www-form-urlencoded` (OAuth2 Password: `username`, `password`) → `{"access_token": "...", "token_type": "bearer"}`. Реализация — `base_app/api/api_v1/auth.py`, JWT в `base_app/core/security.py`.

> Убедитесь, что `tokenUrl` в зависимостях (`base_app/core/dependencies.py`) совпадает с фактическим префиксом роутера.

### `/api/v1/users`

- `GET` — список пользователей (`UserRead`), репозиторий: `base_app/crud/user_repository.py:get_all_users`.
- `POST` — создать пользователя (`UserCreate` → User + Profile + базовый Permission).

---

## Модели и права

- **User**: `email` (уникальный), `username` (опц.), `hashed_password`, `is_active`, `activation_key` (+служебные поля).
- **Profile**: 1:1 к `User`; контактные/публичные поля + `verification`.
- **Permission**: связь к `Profile` (практически 1:1), флаги:
  - `is_superadmin`, `is_admin`, `is_staff`, `is_updater`, `is_reader`, `is_user`.

В БД настроены каскадные удаления, а также триггер, удаляющий `User` при удалении связанного `Profile`.

---

## Регистрация моделей в админке (аналог `django admin.py`)

Файл `src/admin.py` содержит минимальный «реестр» моделей:

```python
from src.admin import admin_site
from src.core.models.user import User

admin_site.register(
    User,
    slug="users",
    list_display=["id", "email", "username", "is_active"],
    form_fields=["email", "username", "is_active", "activation_key"],
    readonly_fields=["id"],
    search_fields=["email", "username"],
    can_create=False,
    can_delete=False,
)
```

- **`slug`** определяет часть URL (например, `/admin/m/users`).
- **`list_display`** — колонки списка, **`form_fields`** — редактируемые поля, **`readonly_fields`** — только просмотр.
- Аналогично регистрируются `Profile` и `Permission`.

---

## Загрузка файлов и ограничения

- Каталог: `static/uploads/avatars/`.
- Серверная валидация:
  - MIME‑тип должен начинаться с `image/`;
  - размер ≤ **3 МБ**;
  - геометрия не меньше **40×40 px**.
- При загрузке **предыдущий файл аватара удаляется**.
- На фронте `static/js/avatar-preview.js` показывает превью, имя файла и валидирует ограничения **до** отправки формы; изменения применяются в UI сразу, но сохраняются только после нажатия «Сохранить».

---




## Расширение и доработка

- Добавляйте модели в БД через Alembic, регистрируйте их в `base_app/admin.py` — они появятся в админ‑меню.
- Политики прав можно расширять новыми флагами в `Permission` и проверками во вьюхах.
- Веб‑часть масштабируется через новые шаблоны в `templates/` и статику в `static/`.
- API — подключайте новые роутеры под `base_app/api/api_v1/`, включайте их в `__init__.py`.

---

## Подсказки и устранение проблем

- **.env**: используйте `.env` или `.env.example` без опечаток.
- **Маршруты/префиксы**: следите, чтобы `tokenUrl` и префиксы роутеров совпадали (во избежание «двойного префикса»).
- **CSRF в админке**: логин/формы используют CSRF‑токен; при 400/403 проверьте скрытое поле и сессию.
- **Права не сохраняются**: `is_superadmin` может менять только супер‑админ.
- **Аватар/превью**: проверяйте подключение `static/js/avatar-preview.js` (через `defer`) и кеш браузера.


# Сервис получения ВОР

Создать суперпользователя
```
docker compose exec app bash -lc "python -m src.manage --create_superuser"
```
Залить ФСНБ в Postgres
```
docker compose exec app bash -lc "python -m src.scripts.create_fsnb_pg"
```
Проверить Postgres (таблицы + количество + примеры)
```
docker compose exec pg bash -lc "psql -U user -d shop -c '\dt'"

docker compose exec pg bash -lc "psql -U user -d shop -c 'select count(*) from items;'"

docker compose exec pg bash -lc "psql -U user -d shop -c \"select type, count(*) from items group by type order by 2 desc;\""

docker compose exec pg bash -lc "psql -U user -d shop -c \"select id, code, left(name,120) as name, unit, type from items order by id limit 5;\""
```
Индексация Qdrant
```
docker compose exec app bash -lc "python -m src.scripts.init_vector_db"
```
Проверить Qdrant (с хоста)
### список коллекций (на хосте qdrant проброшен как 6335)
```
curl -s http://127.0.0.1:6335/collections | head
```
### count по коллекции (пример: fsnb_giga)
```
curl -s -X POST "http://127.0.0.1:6335/collections/fsnb_giga/points/count" \
  -H "Content-Type: application/json" \
  -d '{"exact": true}' | head
```
