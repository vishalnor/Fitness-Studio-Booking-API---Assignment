"""Timezone helpers. Storage is always IST (Asia/Kolkata); responses can be converted."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Current time as a naive IST datetime (matches how values are stored)."""
    return datetime.now(IST).replace(tzinfo=None)


def to_ist_naive(dt: datetime) -> datetime:
    """Convert an incoming datetime to naive IST. Naive input is assumed to be IST."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(IST).replace(tzinfo=None)


def from_ist(dt: datetime, tz_name: str | None = None) -> datetime:
    """Take a stored naive-IST datetime and return an aware one in tz_name (default IST)."""
    aware = dt.replace(tzinfo=IST)
    if not tz_name:
        return aware
    return aware.astimezone(get_zone(tz_name))


def get_zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone '{tz_name}'")
