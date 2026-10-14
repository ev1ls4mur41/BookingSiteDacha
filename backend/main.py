"""FastAPI-приложение для сервиса бронирования номеров/квартир."""
import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from sqlalchemy import or_, text
from sqlalchemy.orm import Session, joinedload

from .database import engine, get_db, SessionLocal
from .models import Booking, Listing
from .schemas import (
    AdminLogin,
    AvailabilityRange,
    BookingCreate,
    BookingOut,
    BookingStatusUpdate,
    CalendarDay,
    ListingCreate,
    ListingOut,
    ListingUpdate,
    split_images,
)

# Создаём таблицы при старте
from . import models  # noqa: F401  (регистрирует модели в Base)
from .database import Base

Base.metadata.create_all(bind=engine)


def ensure_schema_upgrades():
    """Мягкая миграция SQLite: добавляем отсутствующие колонки без потери данных."""
    with engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(listings)").fetchall()}
        if "images" not in cols:
            conn.execute(text("ALTER TABLE listings ADD COLUMN images TEXT NOT NULL DEFAULT ''"))


ensure_schema_upgrades()

app = FastAPI(
    title="StayEasy — бронирование номеров и квартир",
    description="API для поиска объектов размещения, проверки доступности и бронирования.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


# ==================== Вспомогательные функции ====================

def nights_count(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def has_overlap(b: Booking, check_in: date, check_out: date) -> bool:
    """Пересечение дат с активной бронью [check_in, check_out)."""
    if b.status == "cancelled":
        return False
    return b.check_in < check_out and b.check_out > check_in


def is_listing_available(db: Session, listing_id: int, check_in: date, check_out: date) -> bool:
    bookings = db.query(Booking).filter(Booking.listing_id == listing_id).all()
    return not any(has_overlap(b, check_in, check_out) for b in bookings)


# ==================== Админ-доступ (простая cookie-сессия) ====================
# Логин задаётся переменными окружения ADMIN_USERNAME / ADMIN_PASSWORD
# (по умолчанию: admin / admin123 — смените в .env на боевом сервере!)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(16))  # пересоздаётся при рестарте
SESSION_COOKIE = "staeasy_admin"
SESSION_TTL_HOURS = 12


def make_session_token(username: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
    payload = f"{username}:{exp.isoformat()}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_token(token: Optional[str]) -> bool:
    if not token or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        username, exp_iso = payload.split(":", 1)
        if username != ADMIN_USERNAME:
            return False
        return datetime.fromisoformat(exp_iso) > datetime.utcnow()
    except ValueError:
        return False


def require_admin(request: Request) -> str:
    """Зависимость: пускает только залогиненного админа."""
    token = request.cookies.get(SESSION_COOKIE)
    if not verify_session_token(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход в админку")
    return token.rsplit(".", 1)[0].split(":", 1)[0]


@app.post("/api/admin/login")
def admin_login(payload: AdminLogin, response: JSONResponse):
    ok_user = hmac.compare_digest(payload.username, ADMIN_USERNAME)
    ok_pass = hmac.compare_digest(payload.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    resp = JSONResponse({"ok": True, "username": ADMIN_USERNAME})
    resp.set_cookie(
        SESSION_COOKIE, make_session_token(ADMIN_USERNAME),
        httponly=True, samesite="lax", max_age=SESSION_TTL_HOURS * 3600, path="/",
    )
    return resp


@app.post("/api/admin/logout")
def admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/admin/me")
def admin_me(request: Request):
    user = require_admin(request)
    return {"username": user}


# ==================== Health / статика ====================

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ==================== Listings ====================

def listing_payload_to_fields(payload) -> dict:
    """Превращает входную схему (ListingCreate/ListingUpdate) в поля ORM.

    Поддерживает несколько картинок: images=[...] или images_raw="url1,url2".
    Первая картинка — обложка (image_url), остальные хранятся в Listing.images.
    """
    data = payload.model_dump(exclude_unset=True)
    images_raw = data.pop("images_raw", None)
    images_list = data.pop("images", None)

    if images_raw is not None or images_list:
        urls = split_images(images_raw) if images_raw else []
        for u in (images_list or []):
            u = (u or "").strip()
            if u and u not in urls:
                urls.append(u)
        urls = urls[:12]
        # если обложку не прислали отдельно — берём первую из списка
        cover = data.get("image_url")
        if cover is None and payload.image_url:
            cover = payload.image_url.strip()
        if not cover and urls:
            cover = urls[0]
        rest = [u for u in urls if u != cover]
        data["image_url"] = cover or ""
        data["images"] = ",".join(rest)
    return data


@app.get("/api/listings", response_model=List[ListingOut])
def list_listings(
    db: Session = Depends(get_db),
    city: Optional[str] = Query(None, description="Город"),
    type: Optional[str] = Query(None, pattern="^(room|apartment)$", description="Тип: room|apartment"),
    guests: Optional[int] = Query(None, ge=1, le=20, description="Минимум гостей"),
    max_price: Optional[float] = Query(None, ge=0, description="Макс. цена за ночь"),
    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
):
    """Поиск объектов размещения с фильтрами и проверкой свободных дат."""
    q = db.query(Listing).filter(Listing.is_active == True)  # noqa: E712
    if city:
        q = q.filter(Listing.city.ilike(f"%{city.strip()}%"))
    if type:
        q = q.filter(Listing.property_type == type)
    if guests:
        q = q.filter(Listing.guests >= guests)
    if max_price is not None:
        q = q.filter(Listing.price_per_night <= max_price)

    results = []
    for l in q.order_by(Listing.rating.desc(), Listing.price_per_night.asc()).all():
        if check_in and check_out:
            if check_out <= check_in:
                raise HTTPException(400, "Дата выезда должна быть позже даты заезда")
            if not is_listing_available(db, l.id, check_in, check_out):
                continue
        results.append(ListingOut.from_orm_any(l))
    return results


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    l = db.query(Listing).get(listing_id)
    if not l or not l.is_active:
        raise HTTPException(404, "Объект не найден")
    return ListingOut.from_orm_any(l)


@app.post("/api/listings", response_model=ListingOut, status_code=201)
def create_listing(payload: ListingCreate, db: Session = Depends(get_db)):
    l = Listing(**listing_payload_to_fields(payload))
    db.add(l)
    db.commit()
    db.refresh(l)
    return ListingOut.from_orm_any(l)


@app.patch("/api/listings/{listing_id}")
def update_listing(listing_id: int, payload: ListingUpdate, db: Session = Depends(get_db)):
    l = db.query(Listing).get(listing_id)
    if not l:
        raise HTTPException(404, "Объект не найден")
    for k, v in listing_payload_to_fields(payload).items():
        setattr(l, k, v)
    db.commit()
    db.refresh(l)
    return ListingOut.from_orm_any(l)


@app.delete("/api/listings/{listing_id}", status_code=204)
def delete_listing(listing_id: int, db: Session = Depends(get_db)):
    l = db.query(Listing).get(listing_id)
    if not l:
        raise HTTPException(404, "Объект не найден")
    db.delete(l)
    db.commit()


@app.get("/api/listings/{listing_id}/availability")
def check_availability(
    listing_id: int,
    check_in: date,
    check_out: date,
    db: Session = Depends(get_db),
):
    """Свободен ли объект на указанный период."""
    l = db.query(Listing).get(listing_id)
    if not l:
        raise HTTPException(404, "Объект не найден")
    if check_out <= check_in:
        raise HTTPException(400, "Дата выезда должна быть позже даты заезда")
    available = is_listing_available(db, listing_id, check_in, check_out)
    return {
        "listing_id": listing_id,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "available": available,
        "nights": nights_count(check_in, check_out),
        "total_price": round(l.price_per_night * nights_count(check_in, check_out), 2),
    }


@app.get("/api/listings/{listing_id}/calendar")
def listing_calendar(
    listing_id: int,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    """
    Публичная занятость объекта на месяц. Возвращает дни с статусом:
    free | booked | past. Используется календарём на карточке объекта,
    чтобы гость видел занятые даты ДО заполнения формы.
    Отменённые брони не учитываются.
    """
    l = db.query(Listing).get(listing_id)
    if not l or not l.is_active:
        raise HTTPException(404, "Объект не найден")

    first = date(year, month, 1)
    next_month = date(year + (month == 12), (month % 12) + 1, 1)
    days_in_month = (next_month - first).days

    bookings = (
        db.query(Booking)
        .filter(
            Booking.listing_id == listing_id,
            Booking.status != "cancelled",
            Booking.check_in < next_month,
            Booking.check_out >= first,
        )
        .all()
    )

    today = date.today()
    result = []
    for i in range(days_in_month):
        d = first + timedelta(days=i)
        # дата выезда существующей брони — сама уже свободна (checkout day)
        booked = any(b.check_in <= d < b.check_out for b in bookings)
        if d < today:
            status_day = "past"
        elif booked:
            status_day = "booked"
        else:
            status_day = "free"
        result.append(CalendarDay(date=d, status=status_day))

    return {
        "listing_id": listing_id,
        "year": year,
        "month": month,
        "min_date": max(today, first).isoformat(),
        "days": result,
    }


# ==================== Bookings ====================

@app.post("/api/bookings", response_model=BookingOut, status_code=201)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    """Создание брони с проверкой существования объекта и пересечения дат."""
    l = db.query(Listing).get(payload.listing_id)
    if not l or not l.is_active:
        raise HTTPException(404, "Объект не найден")
    if payload.check_out <= payload.check_in:
        raise HTTPException(400, "Дата выезда должна быть позже даты заезда")
    if payload.check_in < date.today():
        raise HTTPException(400, "Нельзя забронировать на прошедшую дату")
    if payload.guests > l.guests:
        raise HTTPException(400, f"В объекте максимум {l.guests} гост(-ов)")
    if not is_listing_available(db, l.id, payload.check_in, payload.check_out):
        raise HTTPException(409, "На выбранные даты объект уже занят")

    nights = nights_count(payload.check_in, payload.check_out)
    booking = Booking(
        **payload.model_dump(),
        total_price=round(l.price_per_night * nights, 2),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@app.get("/api/bookings", response_model=List[BookingOut])
def list_bookings(
    db: Session = Depends(get_db),
    listing_id: Optional[int] = None,
    guest_email: Optional[str] = Query(None, description="E-mail гостя"),
    status: Optional[str] = Query(None, pattern="^(pending|confirmed|cancelled)$"),
):
    """
    Публичный список броней доступен ТОЛЬКО по guest_email.
    Полная выдача всех броней — только через /api/admin/bookings.
    """
    if not guest_email:
        raise HTTPException(400, "Укажите guest_email для поиска броней")
    q = db.query(Booking).options(joinedload(Booking.listing)).filter(
        Booking.guest_email == guest_email
    )
    if listing_id:
        q = q.filter(Booking.listing_id == listing_id)
    if status:
        q = q.filter(Booking.status == status)
    return q.order_by(Booking.created_at.desc()).all()


@app.get("/api/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    b = (
        db.query(Booking)
        .options(joinedload(Booking.listing))
        .get(booking_id)
    )
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    return b


# ==================== Админка: брони и объекты ====================

@app.get("/api/admin/stats")
def admin_stats(request: Request, db: Session = Depends(get_db)):
    """Сводка для дашборда админа."""
    require_admin(request)
    from sqlalchemy import func

    def cnt(*conds):
        q = db.query(func.count(Booking.id))
        for c in conds:
            q = q.filter(c)
        return q.scalar() or 0

    today = date.today()
    active_cond = Booking.status != "cancelled"
    revenue = (
        db.query(func.sum(Booking.total_price))
        .filter(Booking.status != "cancelled")
        .scalar() or 0.0
    )
    month_start = today.replace(day=1)
    revenue_month = (
        db.query(func.sum(Booking.total_price))
        .filter(Booking.status != "cancelled", Booking.check_in >= month_start)
        .scalar() or 0.0
    )
    upcoming = cnt(active_cond, Booking.check_in >= today)
    arriving_today = cnt(active_cond, Booking.check_in == today)
    in_stay = cnt(active_cond, Booking.check_in <= today, Booking.check_out > today)

    return {
        "listings_total": db.query(func.count(Listing.id)).scalar() or 0,
        "listings_active": db.query(func.count(Listing.id)).filter(Listing.is_active == True).scalar() or 0,  # noqa: E712
        "bookings_total": cnt(),
        "bookings_pending": cnt(Booking.status == "pending"),
        "bookings_confirmed": cnt(Booking.status == "confirmed"),
        "bookings_cancelled": cnt(Booking.status == "cancelled"),
        "upcoming": upcoming,
        "arriving_today": arriving_today,
        "in_stay": in_stay,
        "revenue_total": round(float(revenue), 2),
        "revenue_month": round(float(revenue_month), 2),
    }


@app.get("/api/admin/bookings", response_model=List[BookingOut])
def admin_list_bookings(
    request: Request,
    db: Session = Depends(get_db),
    listing_id: Optional[int] = None,
    booking_status: Optional[str] = Query(None, alias="status", pattern="^(pending|confirmed|cancelled)$"),
    guest_email: Optional[str] = None,
    search: Optional[str] = Query(None, description="Поиск по имени/телефону/e-mail"),
    check_in_from: Optional[date] = None,
    check_in_to: Optional[date] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    """Все брони с фильтрами — только для админа."""
    require_admin(request)
    q = db.query(Booking).options(joinedload(Booking.listing))
    if listing_id:
        q = q.filter(Booking.listing_id == listing_id)
    if booking_status:
        q = q.filter(Booking.status == booking_status)
    if guest_email:
        q = q.filter(Booking.guest_email == guest_email)
    if search:
        s = f"%{search.strip()}%"
        q = q.filter(or_(Booking.guest_name.ilike(s), Booking.guest_phone.ilike(s), Booking.guest_email.ilike(s)))
    if check_in_from:
        q = q.filter(Booking.check_in >= check_in_from)
    if check_in_to:
        q = q.filter(Booking.check_in <= check_in_to)
    return q.order_by(Booking.check_in.desc()).limit(limit).all()


@app.post("/api/admin/bookings", response_model=BookingOut, status_code=201)
def admin_create_booking(payload: BookingCreate, request: Request, db: Session = Depends(get_db)):
    """Админ может создать бронь вручную (например, по телефону)."""
    require_admin(request)
    return create_booking(payload, db=db)


@app.patch("/api/admin/bookings/{booking_id}/status", response_model=BookingOut)
def admin_update_booking_status(booking_id: int, payload: BookingStatusUpdate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    b = db.query(Booking).options(joinedload(Booking.listing)).get(booking_id)
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    b.status = payload.status
    db.commit()
    db.refresh(b)
    return b


@app.delete("/api/admin/bookings/{booking_id}", status_code=204)
def admin_delete_booking(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """Жёсткое удаление брони (обычно не нужно — используйте отмену)."""
    require_admin(request)
    b = db.query(Booking).get(booking_id)
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    db.delete(b)
    db.commit()


@app.get("/api/admin/listings")
def admin_list_all_listings(request: Request, db: Session = Depends(get_db)):
    """Все объекты, включая неактивные — только для админа."""
    require_admin(request)
    return [ListingOut.from_orm_any(l) for l in db.query(Listing).order_by(Listing.city, Listing.title).all()]


@app.post("/api/admin/listings", status_code=201)
def admin_create_listing(payload: ListingCreate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return create_listing(payload, db=db)


@app.patch("/api/admin/listings/{listing_id}")
def admin_update_listing(listing_id: int, payload: ListingUpdate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return update_listing(listing_id, payload, db=db)


@app.delete("/api/admin/listings/{listing_id}", status_code=204)
def admin_delete_listing(listing_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return delete_listing(listing_id, db=db)


# ==================== Загрузка картинок (для админки) ====================

UPLOAD_DIR = os.path.join(os.path.dirname(FRONTEND_DIR), "uploads")
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 МБ


@app.post("/api/admin/upload-image")
async def admin_upload_image(request: Request, file: UploadFile = File(...)):
    """Загрузка фото объекта: сохраняет файл в ./uploads и отдаёт URL /uploads/..."""
    require_admin(request)
    import posixpath

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"Неподдерживаемый формат: {ext or 'без расширения'}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Файл больше 8 МБ")
    if not data:
        raise HTTPException(400, "Пустой файл")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_base = posixpath.basename((file.filename or "image").replace("\\", "/"))
    stem, _ = os.path.splitext(safe_base)
    stem = "".join(c for c in stem if c.isalnum() or c in "-_")[:40] or "image"
    name = f"{datetime.utcnow():%Y%m%d%H%M%S}_{stem}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return {"url": f"/uploads/{name}", "size": len(data)}


@app.patch("/api/bookings/{booking_id}/status", response_model=BookingOut)
def update_booking_status(booking_id: int, payload: BookingStatusUpdate, request: Request, db: Session = Depends(get_db)):
    """Смена статуса доступна только админу (см. также /api/admin/bookings/...)."""
    require_admin(request)
    b = db.query(Booking).options(joinedload(Booking.listing)).get(booking_id)
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    b.status = payload.status
    db.commit()
    db.refresh(b)
    return b


@app.delete("/api/bookings/{booking_id}", status_code=204)
def cancel_booking(booking_id: int, guest_email: str = Query(..., description="E-mail гостя для подтверждения"), db: Session = Depends(get_db)):
    """Отмена брони гостем — только своей (совпадение e-mail)."""
    b = db.query(Booking).get(booking_id)
    if not b or b.guest_email != guest_email:
        raise HTTPException(404, "Бронь не найдена")
    b.status = "cancelled"
    db.commit()


# ==================== Страницы ====================

@app.get("/admin")
def serve_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


# ==================== Демо-данные ====================

def seed_demo_data():
    db = SessionLocal()
    try:
        if db.query(Listing).count() > 0:
            return
        demo = [
            dict(title="Уютная студия в центре", property_type="apartment", city="Москва",
                 address="ул. Тверская, 12", guests=2, bedrooms=1, price_per_night=4500, rating=4.8,
                 image_url="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=70",
                 images="https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&q=70, https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800&q=70",
                 description="Светлая студия с панорамными окнами в 5 минутах от метро. Идеальна для пар и командировок.",
                 amenities="Wi-Fi, Кухня, Стиральная машина, Кондиционер"),
            dict(title="2-комнатная квартира у парка", property_type="apartment", city="Санкт-Петербург",
                 address="Московский пр., 45", guests=4, bedrooms=2, price_per_night=6200, rating=4.7,
                 image_url="https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&q=70",
                 images="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800&q=70, https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=70",
                 description="Просторная квартира рядом с парком Победы. Тихий двор, всё необходимое для семьи.",
                 amenities="Wi-Fi, Кухня, Балкон, Парковка"),
            dict(title="Стандартный номер в отеле «Волна»", property_type="room", city="Сочи",
                 address="Черноморская ул., 7", guests=2, bedrooms=1, price_per_night=3800, rating=4.5,
                 image_url="https://images.unsplash.com/photo-1611892440504-42a792e24d32?w=800&q=70",
                 images="https://images.unsplash.com/photo-1590490360182-c33fe51c6fbd?w=800&q=70, https://images.unsplash.com/photo-1584132967334-10e017469f7f?w=800&q=70",
                 description="Комфортный номер с видом на море, завтрак включён, до пляжа 3 минуты пешком.",
                 amenities="Wi-Fi, Завтрак, Кондиционер, Бассейн"),
            dict(title="Лофт с террасой", property_type="apartment", city="Казань",
                 address="ул. Баумана, 28", guests=3, bedrooms=1, price_per_night=5100, rating=4.9,
                 image_url="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800&q=70",
                 images="https://images.unsplash.com/photo-1493809842364-78817addd179?w=800&q=70, https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=70",
                 description="Дизайнерский лофт в историческом центре. Большая терраса с видом на Кремль.",
                 amenities="Wi-Fi, Кухня, Терраса, Кофемашина"),
            dict(title="Эконом номер с односпальной кроватью", property_type="room", city="Нижний Новгород",
                 address="ул. Большая Покровская, 3", guests=1, bedrooms=1, price_per_night=1900, rating=4.2,
                 image_url="https://images.unsplash.com/photo-1595576501825-4044aebc4f2b?w=800&q=70",
                 images="https://images.unsplash.com/photo-1595576501825-4044aebc4f2b?w=800&q=70, https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=800&q=70",
                 description="Бюджетный вариант в самом сердце города. Чисто, тихо, рядом кафе и транспорт.",
                 amenities="Wi-Fi, Душ, ТВ"),
            dict(title="Таунхаус у моря", property_type="apartment", city=" Калининград".strip(),
                 address="Курская коса, 12", guests=6, bedrooms=3, price_per_night=9800, rating=4.9,
                 image_url="https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=70",
                 images="https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&q=70, https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=800&q=70",
                 description="Двухэтажный домик на берегу Балтики. Камин, гриль, собственный выход к пляжу.",
                 amenities="Wi-Fi, Кухня, Камин, Парковка, Гриль"),
        ]
        for item in demo:
            db.add(Listing(**item))
        db.commit()
    finally:
        db.close()


seed_demo_data()

# Загруженные через админку фото отдаём из ./uploads
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Статические ассеты фронтенда (css/js/img) — подключаем в конце,
# чтобы API-маршруты имели приоритет.
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
