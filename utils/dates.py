from __future__ import annotations

from datetime import datetime

import pytz


def tzinfo(tzname: str):
    return pytz.timezone(tzname)


def to_tz(dt: datetime, tzname: str) -> datetime:
    tz = tzinfo(tzname)
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt.astimezone(tz)


def parse_datetime_local(value: str, tzname: str) -> str | None:
    """Convierte 'YYYY-MM-DDTHH:MM' (datetime-local) a ISO UTC."""
    if not value:
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    tz = tzinfo(tzname)
    aware_local = tz.localize(naive)
    return aware_local.astimezone(pytz.UTC).isoformat()


def fmt_datetime_local(iso_dt: str | None, tzname: str) -> str:
    """Para precargar <input type=datetime-local> desde ISO UTC."""
    if not iso_dt:
        return ""
    tz = tzinfo(tzname)
    try:
        dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
    except Exception:
        return ""
    return dt.astimezone(tz).strftime("%Y-%m-%dT%H:%M")


def fmt_date_short(iso_dt: str | None, fallback: str = "—") -> str:
    if not iso_dt:
        return fallback
    try:
        dt = datetime.fromisoformat(iso_dt.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return fallback


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat()
