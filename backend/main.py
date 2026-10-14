"""FastAPI-приложение для сервиса бронирования номеров/квартир."""
import os
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .database import engine, get_db, SessionLocal
from .models import Booking, Listing
from .schemas import (
    AvailabilityRange,
    BookingCreate,
    BookingOut,
    BookingStatusUpdate,
    ListingCreate,
    ListingOut,
    ListingUpdate,
)

# Создаём таблицы при старте
from . import models  # noqa: F401  (регистрирует модели в Base)
from .database import Base

Base.metadata.create_all(bind=engine)

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


# ==================== Health / статика ====================

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ==================== Listings ====================

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
        results.append(l)
    return results


@app.get("/api/listings/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    l = db.query(Listing).get(listing_id)
    if not l or not l.is_active:
        raise HTTPException(404, "Объект не найден")
    return l


@app.post("/api/listings", response_model=ListingOut, status_code=201)
def create_listing(payload: ListingCreate, db: Session = Depends(get_db)):
    l = Listing(**payload.model_dump())
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


@app.patch("/api/listings/{listing_id}", response_model=ListingOut)
def update_listing(listing_id: int, payload: ListingUpdate, db: Session = Depends(get_db)):
    l = db.query(Listing).get(listing_id)
    if not l:
        raise HTTPException(404, "Объект не найден")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(l, k, v)
    db.commit()
    db.refresh(l)
    return l


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
    guest_email: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(pending|confirmed|cancelled)$"),
):
    q = db.query(Booking).options(joinedload(Booking.listing))
    if listing_id:
        q = q.filter(Booking.listing_id == listing_id)
    if guest_email:
        q = q.filter(Booking.guest_email == guest_email)
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


@app.patch("/api/bookings/{booking_id}/status", response_model=BookingOut)
def update_booking_status(booking_id: int, payload: BookingStatusUpdate, db: Session = Depends(get_db)):
    b = db.query(Booking).options(joinedload(Booking.listing)).get(booking_id)
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    b.status = payload.status
    db.commit()
    db.refresh(b)
    return b


@app.delete("/api/bookings/{booking_id}", status_code=204)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    """Отмена брони (мягкая: статус cancelled)."""
    b = db.query(Booking).get(booking_id)
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    b.status = "cancelled"
    db.commit()


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
                 description="Светлая студия с панорамными окнами в 5 минутах от метро. Идеальна для пар и командировок.",
                 amenities="Wi-Fi, Кухня, Стиральная машина, Кондиционер"),
            dict(title="2-комнатная квартира у парка", property_type="apartment", city="Санкт-Петербург",
                 address="Московский пр., 45", guests=4, bedrooms=2, price_per_night=6200, rating=4.7,
                 image_url="https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&q=70",
                 description="Просторная квартира рядом с парком Победы. Тихий двор, всё необходимое для семьи.",
                 amenities="Wi-Fi, Кухня, Балкон, Парковка"),
            dict(title="Стандартный номер в отеле «Волна»", property_type="room", city="Сочи",
                 address="Черноморская ул., 7", guests=2, bedrooms=1, price_per_night=3800, rating=4.5,
                 image_url="https://images.unsplash.com/photo-1611892440504-42a792e24d32?w=800&q=70",
                 description="Комфортный номер с видом на море, завтрак включён, до пляжа 3 минуты пешком.",
                 amenities="Wi-Fi, Завтрак, Кондиционер, Бассейн"),
            dict(title="Лофт с террасой", property_type="apartment", city="Казань",
                 address="ул. Баумана, 28", guests=3, bedrooms=1, price_per_night=5100, rating=4.9,
                 image_url="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800&q=70",
                 description="Дизайнерский лофт в историческом центре. Большая терраса с видом на Кремль.",
                 amenities="Wi-Fi, Кухня, Терраса, Кофемашина"),
            dict(title="Эконом номер с односпальной кроватью", property_type="room", city="Нижний Новгород",
                 address="ул. Большая Покровская, 3", guests=1, bedrooms=1, price_per_night=1900, rating=4.2,
                 image_url="https://images.unsplash.com/photo-1595576501825-4044aebc4f2b?w=800&q=70",
                 description="Бюджетный вариант в самом сердце города. Чисто, тихо, рядом кафе и транспорт.",
                 amenities="Wi-Fi, Душ, ТВ"),
            dict(title="Таунхаус у моря", property_type="apartment", city=" Калининград".strip(),
                 address="Курская коса, 12", guests=6, bedrooms=3, price_per_night=9800, rating=4.9,
                 image_url="https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=70",
                 description="Двухэтажный домик на берегу Балтики. Камин, гриль, собственный выход к пляжу.",
                 amenities="Wi-Fi, Кухня, Камин, Парковка, Гриль"),
        ]
        for item in demo:
            db.add(Listing(**item))
        db.commit()
    finally:
        db.close()


seed_demo_data()

# Статические ассеты фронтенда (css/js/img) — подключаем в конце,
# чтобы API-маршруты имели приоритет.
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
