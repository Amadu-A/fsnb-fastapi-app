# CODE STYLE / ARCHITECTURE (fsnb-fastapi-app)

Документ фиксирует архитектурные правила проекта, чтобы код оставался единообразным, тестируемым и поддерживаемым.

---

## 1) Общая структура слоёв

Проект разделён на 3 основных слоя:

1. **Transport / HTTP слой**
   - `src/**/views/` — HTML (Jinja2) страницы
   - `src/**/api/api_v1/` — JSON / файлы (API v1)

2. **Business / Service слой**
   - `src/**/services/` — бизнес-логика (use-cases)
   - сервисы не знают про шаблоны, не формируют HTTP-ответы

3. **Data Access / Repository слой**
   - `src/crud/` — только SQLAlchemy запросы к БД
   - доступ к БД из сервисов — только через репозитории (DI-контракт)

---

## 2) Жёсткое правило: SQLAlchemy только в crud

✅ Разрешено:
- `select()/update()/delete()/insert()` только в `src/crud/**.py`

❌ Запрещено:
- `session.execute(...)`
- `select(...)`, `update(...)`, `delete(...)`
- `sqlalchemy.inspection.inspect`, `func.count`
в `views/`, `api/`, `services/`

Исключения:
- **миграции** (Alembic) и **скрипты** (`src/scripts/`) — допускается прямой SQL/ORM.

---

## 3) Разделение `views` и `api`

### `views` (HTML)
Папки: `src/core/views/`, `src/train/views/`, etc.

- Возвращают `TemplateResponse`, `RedirectResponse`
- Используют `request.session`, CSRF, формы (`Form`, `UploadFile`)
- Держат логику "страниц": GET показать, POST обработать форму
- НЕ содержат SQL напрямую

### `api` (JSON/Files)
Папки: `src/train/api/api_v1/`, `src/**/api/api_v1/`

- Возвращают `JSONResponse`, `StreamingResponse`, используют `HTTPException`
- Держат версионирование: `/api/v1/...`
- Предназначены для JS/интеграций
- НЕ содержат SQL напрямую

### Правило
Если функциональность нужна и странице, и API:
- делаем **два роутера**, но оба вызывают **один сервис**.

---

## 4) DI и репозитории (Protocol)

### Контракт
Для каждого репозитория есть интерфейс (Protocol), например:
- `IItemRepository`
- `IFeedbackSessionRepository`
- `IFeedbackRowRepository`
- `IFeedbackCandidateRepository`
- `IFeedbackLabelRepository`

Сервис принимает **интерфейс**, а не реализацию.

✅ Хорошо:
```py
class ReviewService:
    def __init__(self, *, item_repo: IItemRepository) -> None:
        self._item_repo = item_repo
```

❌ Плохо:
```py
class ReviewService:
    def __init__(self):
        self._item_repo = ItemRepository()  # жёсткая зависимость
```

### Где создаём реализации
- В `views/api` (composition root) создаём конкретные репозитории и передаём в сервисы.
- В тестах подменяем на fake/mock.

---

## 5) Роутеры: что в них можно и нельзя

### Роутер должен:
- Провалидировать входные данные (минимально)
- Достать actor / session / csrf
- Вызвать сервис
- Вернуть ответ

### Роутер НЕ должен:
- Писать сложную бизнес-логику
- Делать SQL запросы
- Формировать сложные структуры данных "по месту", если это use-case (лучше в сервис)

---

## 6) Сервисы: что в них можно и нельзя

Сервис — это use-case.

### Сервис может:
- Делать оркестрацию: несколько репозиториев, правила, проверки
- Нормализовать/валидировать доменные данные
- Готовить DTO для транспорта (словари/датаклассы)

### Сервис не должен:
- Возвращать `Response`
- Знать про `Request`, cookies, сессии
- Зависеть от шаблонов/Jinja2

---

## 7) Транзакции

Правило: транзакцией управляет **transport слой** (views/api), а не сервис.

✅ Хорошо:
```py
async with session.begin():
    await persist_svc.persist_commit(...)
```

❌ Плохо:
```py
async def persist_commit(...):
    async with session.begin():  # сервис сам открывает транзакцию
        ...
```

Причина: transport слой контролирует границы операции HTTP-запроса.

---

## 8) Именование и стиль (PEP8)

- Имена переменных/функций: `snake_case`
- Классы: `CamelCase`
- Константы: `UPPER_CASE`
- Типизация обязательна для публичных методов сервисов/репозиториев
- `Any` использовать только на границе (например, входящий payload от UI)

---

## 9) Логирование

- Используем единый логгер `get_logger(...)`
- Логи — структурированные (dict payload), ключ `event` обязателен

✅ Пример:
```py
log.info({"event": "review_committed", "session_id": session_id, "rows": len(rows)})
```

---

## 10) Pydantic схемы

- Для API-ответов/запросов используем pydantic модели в `schemas.py` (или `api/schemas.py`)
- Для views (Jinja2) можно передавать dict в контекст, но лучше держать структуру стабильной

---

## 11) Правила по train/review (важные)

- `POST /create` создаёт draft `FeedbackSession` + rows + candidates
- `POST /commit`:
  - пишет labels в **существующую** сессию (`session_id`)
  - делает commit идемпотентным (перезаписывает метки)
  - переводит `FeedbackSession.status = closed`
  - НЕ создаёт новую сессию, НЕ дублирует кандидатов

---

## 12) Checklist для PR

Перед PR проверить:

- [ ] Нет `select/update/delete/execute` вне `src/crud`
- [ ] Роутеры тонкие: вход → сервис → ответ
- [ ] Сервисы не знают про HTTP
- [ ] DI соблюдён: сервисы принимают интерфейсы репозиториев
- [ ] Транзакции открываются в роутере (views/api)
- [ ] Логи структурированы и имеют `event`

---

## 13) Где что лежит (быстрый ориентир)

- `src/core/views/` — страницы (auth/admin/профиль и т.д.)
- `src/train/views/` — страницы train/review
- `src/train/api/api_v1/` — API train/review
- `src/train/services/` — сервисы review/persist/report
- `src/crud/` — репозитории (SQLAlchemy)
- `src/templates/` — Jinja2 шаблоны
- `src/static/` — JS/CSS

---