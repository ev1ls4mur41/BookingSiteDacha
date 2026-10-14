# StayEasy 🏠 — сайт бронирования номеров и квартир

Минималистичный сервис для бронирования **номеров** (отели) и **квартир**: поиск с фильтрами, проверка свободных дат, оформление и отмена брони.

## Стек

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite
- **Frontend:** HTML / CSS / JavaScript (без сборки), served тем же сервером

## Структура

```
backend/        # FastAPI-приложение (models, schemas, API)
frontend/       # index.html + style.css + app.js
requirements.txt
```

## Запуск

### Windows (Git Bash)

```bash
python -m venv .venv
source .venv/Scripts/activate   # если не работает: .venv/Scripts/activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

> Важно: запускайте команды из корня проекта (там, где лежит `requirements.txt`).
> Если команда `uvicorn` не найдена — используйте `python -m uvicorn ...`, это работает всегда.

Откройте:

- Сайт: http://localhost:8000/
- Swagger API: http://localhost:8000/docs

При первом запуске автоматически создаётся база `bookings.db` с демо-объектами (6 квартир/номеров по разным городам).

## Возможности

### Поиск и просмотр
- Фильтры: город, тип (квартира/номер), даты заезда/выезда, количество гостей, максимальная цена
- Фильтр по датам исключает занятые объекты (проверка пересечений броней)
- Карточка объекта: фото, описание, удобства, рейтинг, цена за ночь

### Бронирование
- Форма: имя, телефон, e-mail, даты, гости, комментарий
- Контроль на сервере: корректность дат, прошедшие даты, вместимость, **конфликт с существующими бронями (409)**
- Автоматический расчёт итоговой стоимости (ночи × цена)

### Мои брони
- Поиск броней по e-mail
- Статусы: ожидает / подтверждена / отменена
- Отмена брони (мягкое удаление — даты освобождаются)

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/listings` | Список объектов + фильтры (`city`, `type`, `guests`, `max_price`, `check_in`, `check_out`) |
| GET | `/api/listings/{id}` | Карточка объекта |
| POST | `/api/listings` | Создать объект |
| PATCH | `/api/listings/{id}` | Обновить объект |
| DELETE | `/api/listings/{id}` | Удалить объект |
| GET | `/api/listings/{id}/availability?check_in=&check_out=` | Проверка свободных дат + итоговая цена |
| POST | `/api/bookings` | Создать бронь |
| GET | `/api/bookings` | Список броней (`listing_id`, `guest_email`, `status`) |
| GET | `/api/bookings/{id}` | Детали брони |
| PATCH | `/api/bookings/{id}/status` | Изменить статус брони |
| DELETE | `/api/bookings/{id}` | Отменить бронь |
| GET | `/api/health` | Проверка работоспособности |

Полная интерактивная документация — в Swagger UI (`/docs`).
