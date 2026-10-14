"""Pydantic-схемы запросов/ответов API."""
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


# ---------- Listings ----------

class ListingBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    property_type: str = Field(default="room", pattern="^(room|apartment)$")
    city: str = Field(min_length=2, max_length=100)
    address: str = ""
    guests: int = Field(default=2, ge=1, le=20)
    bedrooms: int = Field(default=1, ge=0, le=20)
    price_per_night: float = Field(default=0, ge=0)
    image_url: str = ""
    amenities: str = ""


class ListingCreate(ListingBase):
    pass


class ListingUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = None
    property_type: Optional[str] = Field(default=None, pattern="^(room|apartment)$")
    city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    address: Optional[str] = None
    guests: Optional[int] = Field(default=None, ge=1, le=20)
    bedrooms: Optional[int] = Field(default=None, ge=0, le=20)
    price_per_night: Optional[float] = Field(default=None, ge=0)
    image_url: Optional[str] = None
    amenities: Optional[str] = None
    is_active: Optional[bool] = None


class ListingOut(ListingBase):
    id: int
    rating: float
    is_active: bool
    created_at: datetime

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
