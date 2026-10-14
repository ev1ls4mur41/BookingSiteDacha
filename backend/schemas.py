"""Pydantic-схемы запросов/ответов API."""
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


# ---------- Listings ----------

MAX_IMAGES = 12


def split_images(raw: str) -> List[str]:
    """Список URL из строки через запятую/перевод строки (без пустых)."""
    parts = []
    for chunk in (raw or "").replace("\n", ",").split(","):
        p = chunk.strip()
        if p:
            parts.append(p)
    return parts


class ListingBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    property_type: str = Field(default="room", pattern="^(room|apartment)$")
    city: str = Field(min_length=2, max_length=100)
    address: str = ""
    guests: int = Field(default=2, ge=1, le=20)
    bedrooms: int = Field(default=1, ge=0, le=20)
    price_per_night: float = Field(default=0, ge=0)
    rating: float = Field(default=4.5, ge=0, le=5)
    image_url: str = ""
    amenities: str = ""


class ListingIn(ListingBase):
    """Входные данные: картинки можно прислать списком ИЛИ одной строкой."""
    images: List[str] = Field(default_factory=list, max_length=MAX_IMAGES)
    images_raw: Optional[str] = None  # "url1,url2" — удобно из админ-формы

    @field_validator("images")
    @classmethod
    def clean_urls(cls, v: List[str]) -> List[str]:
        out = []
        for u in v:
            u = (u or "").strip()
            if not u:
                continue
            if not u.startswith(("http://", "https://", "/")):
                raise ValueError(f"Некорректный URL картинки: {u[:60]}")
            if len(u) > 500:
                raise ValueError("Слишком длинный URL картинки")
            out.append(u)
        return out


class ListingCreate(ListingIn):
    pass


class ListingUpdate(ListingIn):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = None
    property_type: Optional[str] = Field(default=None, pattern="^(room|apartment)$")
    city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    address: Optional[str] = None
    guests: Optional[int] = Field(default=None, ge=1, le=20)
    bedrooms: Optional[int] = Field(default=None, ge=0, le=20)
    price_per_night: Optional[float] = Field(default=None, ge=0)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    image_url: Optional[str] = None
    amenities: Optional[str] = None
    is_active: Optional[bool] = None


class ListingOut(ListingBase):
    id: int
    is_active: bool
    created_at: datetime
    images: List[str] = []

    @classmethod
    def from_orm_any(cls, l) -> "ListingOut":
        """Собирает ответ из ORM-объекта: images = image_url + список images."""
        extra = split_images(getattr(l, "images", "") or "")
        all_imgs = ([l.image_url] if l.image_url else []) + [u for u in extra if u != l.image_url]
        return cls(
            id=l.id, title=l.title, description=l.description,
            property_type=l.property_type, city=l.city, address=l.address,
            guests=l.guests, bedrooms=l.bedrooms, price_per_night=l.price_per_night,
            rating=l.rating, image_url=l.image_url, amenities=l.amenities,
            is_active=l.is_active, created_at=l.created_at, images=all_imgs,
        )

    class Config:
        from_attributes = True


# ---------- Bookings ----------

class BookingCreate(BaseModel):
    listing_id: int
    guest_name: str = Field(min_length=2, max_length=120)
    guest_phone: str = Field(min_length=5, max_length=50)
    guest_email: str = Field(max_length=120)
    check_in: date
    check_out: date
    guests: int = Field(default=1, ge=1, le=20)
    comment: str = ""

    @field_validator("check_out")
    @classmethod
    def check_dates(cls, v, info):
        ci = info.data.get("check_in")
        if ci is not None and v <= ci:
            raise ValueError("Дата выезда должна быть позже даты заезда")
        return v

    @field_validator("guest_email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Некорректный e-mail")
        return v


class BookingStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|confirmed|cancelled)$")


class BookingOut(BaseModel):
    id: int
    listing_id: int
    guest_name: str
    guest_phone: str
    guest_email: str
    check_in: date
    check_out: date
    guests: int
    total_price: float
    status: str
    comment: str
    created_at: datetime
    listing: Optional[ListingOut] = None

    class Config:
        from_attributes = True


class AvailabilityRange(BaseModel):
    check_in: date
    check_out: date


class ErrorDetail(BaseModel):
    detail: str


# ---------- Календарь / админка ----------

class CalendarDay(BaseModel):
    date: date
    status: str  # free | booked | past


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
