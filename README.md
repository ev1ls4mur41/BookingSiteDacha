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
- Отмена брони (мягкое удаление — даты освобождаются, требуется совпадение e-mail)

### Календарь занятости (на странице объекта)
- Красивый кастомный календарь: свободные / занятые / прошедшие дни
- Гость выбирает даты прямо в календаре — пересечься с занятыми днями невозможно
- Занятые дни недоступны для клика; при выборе диапазона проверяются все ночи между датами
- День выезда предыдущей брони считается свободным (стандартная практика)
- Отменённые брони в календаре не учитываются (даты сразу освобождаются)
- Live-проверка доступности при ручной смене дат в форме бронирования

### Админка (`/admin`)
- Вход по логину/паролю (cookie-сессия на 12 часов)
- **Дашборд:** выручка (всего/за месяц), ждут подтверждения, заездов сегодня, сейчас живут, будущие брони, ближайшие заезды
- **Брони:** таблица всех броней с фильтрами (поиск по имени/телефону/e-mail, статус, объект, период заезда), смена статуса одним кликом, жёсткое удаление
- **Объекты:** список всех объектов (включая скрытые), показ/скрытие с витрины
- Логин задаётся переменными окружения (по умолчанию `admin` / `admin123` — **смените на боевом сервере!**):

```bash
# Linux
ADMIN_USERNAME=mylogin ADMIN_PASSWORD=secretpass python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
# Windows (Git Bash)
export ADMIN_USERNAME=mylogin ADMIN_PASSWORD=secretpass
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/listings` | Список объектов + фильтры (`city`, `type`, `guests`, `max_price`, `check_in`, `check_out`) |
| GET | `/api/listings/{id}` | Карточка объекта |
| POST | `/api/listings` | Создать объект |
| PATCH | `/api/listings/{id}` | Обновить объект |
| DELETE | `/api/listings/{id}` | Удалить объект |
| GET | `/api/listings/{id}/availability?check_in=&check_out=` | Проверка свободных дат + итоговая цена |
| GET | `/api/listings/{id}/calendar?year=&month=` | **Занятость по дням на месяц (публично)** |
| POST | `/api/bookings` | Создать бронь |
| GET | `/api/bookings?guest_email=` | Список броней гостя (только по e-mail) |
| GET | `/api/bookings/{id}` | Детали брони |
| PATCH | `/api/bookings/{id}/status` | Изменить статус брони (только админ) |
| DELETE | `/api/bookings/{id}?guest_email=` | Отменить бронь (только своей e-mail) |
| POST | `/api/admin/login` | Вход в админку |
| POST | `/api/admin/logout` | Выход |
| GET | `/api/admin/me` | Проверка сессии |
| GET | `/api/admin/stats` | Сводка для дашборда |
| GET | `/api/admin/bookings` | Все брони + фильтры (`search`, `status`, `listing_id`, `check_in_from/to`) |
| POST | `/api/admin/bookings` | Создать бронь вручную |
| PATCH | `/api/admin/bookings/{id}/status` | Смена статуса |
| DELETE | `/api/admin/bookings/{id}` | Жёсткое удаление брони |
| GET | `/api/admin/listings` | Все объекты (включая скрытые) |
| POST/PATCH/DELETE | `/api/admin/listings[/{id}]` | Управление объектами |
| GET | `/api/health` | Проверка работоспособности |

Полная интерактивная документация — в Swagger UI (`/docs`).
