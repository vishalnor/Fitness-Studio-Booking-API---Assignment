"""Booking endpoints."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import get_current_user
from ..models import Booking, FitnessClass, User
from ..timeutils import from_ist, get_zone, now_ist

logger = logging.getLogger("fitness.bookings")
router = APIRouter(tags=["bookings"])


def _out(b: Booking, tz: str | None) -> schemas.BookingOut:
    c = b.fitness_class
    return schemas.BookingOut(
        id=b.id,
        class_id=c.id,
        class_name=c.name,
        instructor=c.instructor,
        dateTime=from_ist(c.date_time, tz),
        client_name=b.client_name,
        client_email=b.client_email,
        booked_at=from_ist(b.created_at, tz),
    )


@router.post("/book", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def book_class(
    body: schemas.BookRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cls = db.get(FitnessClass, body.class_id)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Class not found")
    if cls.date_time <= now_ist():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Class has already started or finished")
    already = db.scalar(
        select(Booking).where(Booking.user_id == user.id, Booking.class_id == cls.id)
    )
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already booked this class")

    # Atomic conditional decrement: only succeeds if a slot remains, so concurrent
    # requests can never push availableSlots below zero (no overbooking).
    result = db.execute(
        update(FitnessClass)
        .where(FitnessClass.id == cls.id, FitnessClass.available_slots > 0)
        .values(available_slots=FitnessClass.available_slots - 1)
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "No slots available for this class")

    booking = Booking(
        user_id=user.id,
        class_id=cls.id,
        client_name=body.client_name.strip(),
        client_email=body.client_email.lower(),
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent duplicate request slipped past the check above; the whole
        # transaction (including the slot decrement) is rolled back.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already booked this class")
    db.refresh(booking)
    logger.info("user=%s booked class=%s", user.id, cls.id)
    return _out(booking, None)


@router.get("/bookings", response_model=list[schemas.BookingOut])
def my_bookings(
    tz: str | None = Query(None, description="IANA timezone for the response (default IST)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if tz:
        try:
            get_zone(tz)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    rows = db.scalars(
        select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())
    ).all()
    return [_out(b, tz) for b in rows]
