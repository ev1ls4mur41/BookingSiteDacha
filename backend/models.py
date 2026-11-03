"""ORM-модели: объекты размещения (номера/квартиры) и брони."""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Property(Base):
    """Объект размещения — здание/база с одним адресом (у нас их три).

    Номера и квартиры (Listing) теперь привязываются к объекту, а не хранят
    город/адрес у себя. Это позволяет в админке выбирать объект при создании
    номера, а на сайте фильтровать сразу по объекту.
    """
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    address = Column(String(300), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    listings = relationship("Listing", back_populates="property")


class Listing(Base):
    """Номер или квартира внутри объекта размещения."""
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    property_type = Column(String(20), nullable=False, default="room")  # room | apartment
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True, index=True)
    # устаревшие поля: до миграции данные перенесены в Property; оставлены,
    # чтобы старая БД не ломалась при чтении
    city = Column(String(100), nullable=False, default="", index=True)
    address = Column(String(300), nullable=False, default="")
    guests = Column(Integer, nullable=False, default=2)          # вместимость
    bedrooms = Column(Integer, nullable=False, default=1)
    price_per_night = Column(Float, nullable=False, default=0)   # цена за ночь, руб.
    rating = Column(Float, nullable=False, default=4.5)
    image_url = Column(String(500), nullable=False, default="")   # главная (обложка)
    images = Column(Text, nullable=False, default="")             # все фото: URL через запятую
    amenities = Column(String(500), nullable=False, default="")  # через запятую
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="listing", cascade="all, delete-orphan")
    property = relationship("Property", back_populates="listings")


class Booking(Base):
    """Бронь объекта размещения."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False, index=True)
    guest_name = Column(String(120), nullable=False)
    guest_phone = Column(String(50), nullable=False)
    guest_email = Column(String(120), nullable=False)
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    guests = Column(Integer, nullable=False, default=1)
    total_price = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")  # pending|confirmed|cancelled
    comment = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    listing = relationship("Listing", back_populates="bookings")
