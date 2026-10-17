"""Fitness class endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..deps import get_current_user
from ..models import FitnessClass, User
from ..timeutils import from_ist, get_zone, now_ist, to_ist_naive

router = APIRouter(prefix="/classes", tags=["classes"])


def to_out(c: FitnessClass, tz: str | None = None) -> schemas.ClassOut:
    return schemas.ClassOut(
        id=c.id,
        name=c.name,
        dateTime=from_ist(c.date_time, tz),
        instructor=c.instructor,
        availableSlots=c.available_slots,
    )


@router.post("", response_model=schemas.ClassOut, status_code=status.HTTP_201_CREATED)
def create_class(
    body: schemas.ClassCreate,
    tz: str | None = Query(None, description="IANA timezone for the response, e.g. America/New_York"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if tz:
        _validate_tz(tz)
    when = to_ist_naive(body.dateTime)
    if when <= now_ist():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Class dateTime must be in the future")
    cls = FitnessClass(
        name=body.name.strip(),
        date_time=when,
        instructor=body.instructor.strip(),
        available_slots=body.availableSlots,
        created_by=user.id,
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)
    return to_out(cls, tz)


@router.get("", response_model=list[schemas.ClassOut])
def list_classes(
    response: Response,
    tz: str | None = Query(None, description="IANA timezone for the response (default IST)"),
    name: str | None = Query(None, min_length=1, max_length=100, description="Case-insensitive name contains"),
    instructor: str | None = Query(None, min_length=1, max_length=100, description="Case-insensitive instructor contains"),
    from_: datetime | None = Query(None, alias="from", description="Only classes at/after this time (naive = IST)"),
    to: datetime | None = Query(None, description="Only classes at/before this time (naive = IST)"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
    db: Session = Depends(get_db),
):
    """List upcoming classes (soonest first) with optional filters and pagination.

    The total number of matches is returned in the `X-Total-Count` header.
    """
    if tz:
        _validate_tz(tz)
    conditions = [FitnessClass.date_time > now_ist()]
    if name:
        conditions.append(FitnessClass.name.ilike(f"%{_escape_like(name)}%", escape="\\"))
    if instructor:
        conditions.append(FitnessClass.instructor.ilike(f"%{_escape_like(instructor)}%", escape="\\"))
    start = to_ist_naive(from_) if from_ else None
    end = to_ist_naive(to) if to else None
    if start and end and start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "'from' must be before 'to'")
    if start:
        conditions.append(FitnessClass.date_time >= start)
    if end:
        conditions.append(FitnessClass.date_time <= end)

    total = db.scalar(select(func.count()).select_from(FitnessClass).where(*conditions))
    rows = db.scalars(
        select(FitnessClass)
        .where(*conditions)
        .order_by(FitnessClass.date_time, FitnessClass.id)
        .limit(limit)
        .offset(offset)
    ).all()
    response.headers["X-Total-Count"] = str(total)
    return [to_out(c, tz) for c in rows]


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validate_tz(tz: str) -> None:
    try:
        get_zone(tz)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
