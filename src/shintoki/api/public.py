from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from shintoki.public import (
    LunarYMD,
    gregorian_to_lunar as _gregorian_to_lunar,
    lunar_months_for_year as _lunar_months_for_year,
    principal_terms_between as _principal_terms_between,
)

ALLOWED_DEGREES = tuple(range(0, 360, 30))
ROKUYO = ("先勝", "友引", "先負", "仏滅", "大安", "赤口")


def gregorian_to_lunar(
    target_date: date,
    tz: str = "Asia/Tokyo",
    ephemeris_path: str | None = None,
) -> LunarYMD:
    """Backward-compatible wrapper around `shintoki.public.gregorian_to_lunar`."""
    return _gregorian_to_lunar(target_date, tz=tz, ephemeris_path=ephemeris_path)


def principal_terms_between(
    start: date,
    end: date,
    tz: str,
    degrees: list[int] | None = None,
    ephemeris_path: str | None = None,
) -> list[dict]:
    """Backward-compatible wrapper returning dict rows for legacy callers."""
    events = _principal_terms_between(
        start,
        end,
        tz=tz,
        degrees=degrees,
        ephemeris_path=ephemeris_path,
    )
    return [asdict(event) for event in events]


def day_calendar(
    target_date: date,
    tz: str = "Asia/Tokyo",
    ephemeris_path: str | None = None,
) -> dict:
    lunar = gregorian_to_lunar(target_date, tz=tz, ephemeris_path=ephemeris_path)
    sekki = principal_terms_between(
        target_date,
        target_date + timedelta(days=1),
        tz=tz,
        degrees=list(ALLOWED_DEGREES),
        ephemeris_path=ephemeris_path,
    )
    return {
        "date": target_date.isoformat(),
        "tz": tz,
        "lunar": asdict(lunar),
        "rokuyo": _rokuyo_name(lunar.month, lunar.day),
        "sekki": sekki,
        "issues": [],
    }


def range_calendar(
    start: date,
    end: date,
    tz: str = "Asia/Tokyo",
    ephemeris_path: str | None = None,
) -> dict:
    if end < start:
        raise ValueError("end must be >= start")

    rows = []
    current = start
    while current <= end:
        rows.append(day_calendar(current, tz=tz, ephemeris_path=ephemeris_path))
        current += timedelta(days=1)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "tz": tz,
        "days": rows,
    }


def lunar_months_for_year(
    year: int,
    tz: str = "Asia/Tokyo",
    window_mode: str = "solstice-to-solstice",
    ephemeris_path: str | None = None,
) -> list[dict]:
    """Legacy helper returning dict rows from public API NamedMonth values."""
    rows = _lunar_months_for_year(year, tz=tz, window_mode=window_mode, ephemeris_path=ephemeris_path)
    return [asdict(row) for row in rows]


def _rokuyo_name(month: int, day: int) -> str:
    return ROKUYO[(month + day - 2) % 6]
