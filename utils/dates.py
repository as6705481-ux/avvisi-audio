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


def fmt_ampm(iso_dt: str | None, tzname: str = "America/Tegucigalpa") -> str:
    """
    Convierte un datetime UTC a hora local en formato AM/PM compacto.
    Ej: '28 Jun · 2pm'  o  '28 Jun · 7:30am'
    """
    if not iso_dt:
        return "—"
    try:
        dt    = datetime.fromisoformat(str(iso_dt).replace("Z", "+00:00"))
        local = dt.astimezone(pytz.timezone(tzname))
        day   = str(local.day)
        month = local.strftime("%b")
        hour  = int(local.strftime("%I"))   # 1-12, no leading zero
        minute= local.strftime("%M")
        ampm  = local.strftime("%p").lower()
        time_str = f"{hour}:{minute}{ampm}" if minute != "00" else f"{hour}{ampm}"
        return f"{day} {month} · {time_str}"
    except Exception:
        return "—"


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat()
