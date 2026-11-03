from datetime import UTC, datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7), name="WIB")


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_wib(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed; store and pass timezone-aware values")
    return dt.astimezone(WIB)


def iso_wib(dt: datetime | None) -> str | None:
    """ISO 8601 with +07:00, as required by the API contract."""
    return None if dt is None else to_wib(dt).isoformat(timespec="seconds")


def wib_day_start_utc(now: datetime | None = None) -> datetime:
    d = to_wib(now or now_utc())
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def floor_10min(dt: datetime) -> datetime:
    return dt.replace(minute=dt.minute - dt.minute % 10, second=0, microsecond=0)


_MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def format_wib_human(dt: datetime) -> str:
    """e.g. '2 Nov 2026 13.40 WIB' for WhatsApp templates."""
    d = to_wib(dt)
    return f"{d.day} {_MONTHS_ID[d.month - 1]} {d.year} {d.hour:02d}.{d.minute:02d} WIB"


def format_decimal_id(value: float, digits: int = 1) -> str:
    """Indonesian decimal comma: 35.1 -> '35,1'."""
    return f"{value:.{digits}f}".replace(".", ",")
