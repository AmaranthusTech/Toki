from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

from shintoki.core.new_moon import SkyfieldNewMoonCalculator
from shintoki.core.solar_terms import PrincipalTermWindowRequest, SkyfieldPrincipalTermCalculator
from shintoki.services.debug_months import run_debug_months
from shintoki.services.doctor import resolve_ephemeris_path

ALLOWED_DEGREES = tuple(range(0, 360, 30))


@dataclass(frozen=True)
class LunarYMD:
    """Lunar date result for a Gregorian day."""

    year: int
    month: int
    day: int
    is_leap: bool


@dataclass(frozen=True)
class TermEvent:
    """Principal term event resolved in UTC and local timezone."""

    degree: int
    utc: str
    jst: str
    local: str
    local_date: str


@dataclass(frozen=True)
class NamedMonth:
    """Named lunar month span used for month/day resolution."""

    span_index: int
    month_no: int
    is_leap: bool
    start_utc: str
    end_utc: str
    start_local_date: str
    end_local_date_exclusive: str
    has_zhongqi: bool
    zhongqi_degrees: list[int]


def gregorian_to_lunar(
    target_date: date,
    tz: str = "Asia/Tokyo",
    *,
    ephemeris_path: str | None = None,
    window_mode: str = "solstice-to-solstice",
) -> LunarYMD:
    """Convert Gregorian date to lunar year-month-day.

    Args:
        target_date: Gregorian date.
        tz: Timezone for local-day interpretation.
        ephemeris_path: Optional path to ephemeris file. Auto-resolved when omitted.
        window_mode: Month-naming span normalization mode.

    Returns:
        LunarYMD
    """
    resolved = _resolve_ephemeris_or_raise(ephemeris_path)
    month = _find_named_month(target_date, tz=tz, ephemeris_path=resolved, window_mode=window_mode)
    if month is None:
        raise ValueError(f"lunar month span not found for date: {target_date.isoformat()}")

    start_local = date.fromisoformat(month.start_local_date)
    lunar_day = (target_date - start_local).days + 1
    if lunar_day <= 0:
        raise ValueError(f"invalid lunar day for date: {target_date.isoformat()}")

    month_no = month.month_no
    lunar_year = target_date.year - 1 if month_no in (11, 12) and target_date.month <= 2 else target_date.year
    return LunarYMD(year=lunar_year, month=month_no, day=lunar_day, is_leap=month.is_leap)


def principal_terms_between(
    start_date: date,
    end_date: date,
    tz: str = "Asia/Tokyo",
    degrees: list[int] | None = None,
    *,
    ephemeris_path: str | None = None,
) -> list[TermEvent]:
    """List principal terms in [start_date, end_date) window.

    Args:
        start_date: Inclusive local date.
        end_date: Exclusive local date.
        tz: Output timezone.
        degrees: Degrees to search. Defaults to 0..330 by 30.
        ephemeris_path: Optional path to ephemeris file.

    Returns:
        Sorted list of TermEvent.
    """
    resolved = _resolve_ephemeris_or_raise(ephemeris_path)
    degree_list = list(ALLOWED_DEGREES if degrees is None else degrees)
    for degree in degree_list:
        if degree not in ALLOWED_DEGREES:
            raise ValueError(f"degree must be in 0..330 by 30: {degree}")

    start_utc, end_utc = _date_window_to_utc(start_date, end_date, tz)
    calculator = SkyfieldPrincipalTermCalculator()
    events: list[TermEvent] = []
    for degree in degree_list:
        rows = calculator.find_events_between(
            PrincipalTermWindowRequest(
                degree=degree,
                tz=tz,
                ephemeris_path=resolved,
                start_utc=start_utc,
                end_utc=end_utc,
            )
        )
        events.extend(
            TermEvent(
                degree=degree,
                utc=row.utc,
                jst=row.jst,
                local=row.local,
                local_date=row.local_date,
            )
            for row in rows
        )
    events.sort(key=lambda e: e.utc)
    return events


def lunar_months_for_year(
    year: int,
    tz: str = "Asia/Tokyo",
    window_mode: str = "solstice-to-solstice",
    *,
    ephemeris_path: str | None = None,
) -> list[NamedMonth]:
    """Return month naming rows for a year window.

    Args:
        year: Target Gregorian year.
        tz: Local timezone.
        window_mode: debug-months normalization mode.
        ephemeris_path: Optional ephemeris file path.

    Returns:
        NamedMonth list.
    """
    resolved = _resolve_ephemeris_or_raise(ephemeris_path)
    rows = _months_for_year(year, tz, resolved, window_mode)
    result: list[NamedMonth] = []
    for row in rows:
        result.append(
            NamedMonth(
                span_index=int(row["span_index"]),
                month_no=int(row["month_no"]),
                is_leap=bool(row["is_leap"]),
                start_utc=row["start_utc"],
                end_utc=row["end_utc"],
                start_local_date=row["start_local_date"],
                end_local_date_exclusive=row["end_local_date_exclusive"],
                has_zhongqi=bool(row["has_zhongqi"]),
                zhongqi_degrees=list(row["zhongqi_degrees"]),
            )
        )
    return result


def _resolve_ephemeris_or_raise(ephemeris_path: str | None) -> str:
    resolved = resolve_ephemeris_path(ephemeris_path)
    if resolved is None:
        raise ValueError("missing ephemeris path")
    return str(resolved)


@lru_cache(maxsize=256)
def _months_for_year(year: int, tz: str, ephemeris_path: str, window_mode: str) -> tuple[dict, ...]:
    payload = run_debug_months(
        new_moon_calculator=SkyfieldNewMoonCalculator(),
        term_calculator=SkyfieldPrincipalTermCalculator(),
        year=year,
        pad_days=60,
        degrees=list(ALLOWED_DEGREES),
        tz=tz,
        ephemeris_path=ephemeris_path,
        only_anomalies=False,
        strict_expect_leap=False,
        window_mode=window_mode,
    )
    return tuple(payload["months"])


def _find_named_month(target_date: date, *, tz: str, ephemeris_path: str, window_mode: str) -> NamedMonth | None:
    for year in (target_date.year - 1, target_date.year, target_date.year + 1):
        for month in lunar_months_for_year(year, tz=tz, window_mode=window_mode, ephemeris_path=ephemeris_path):
            start_date = date.fromisoformat(month.start_local_date)
            end_date_exclusive = date.fromisoformat(month.end_local_date_exclusive)
            if start_date <= target_date < end_date_exclusive:
                return month
    return None


def _date_window_to_utc(start_date: date, end_date: date, tz: str) -> tuple[datetime, datetime]:
    tzinfo = ZoneInfo(tz)
    start_dt = datetime.combine(start_date, time.min, tzinfo=tzinfo)
    end_dt = datetime.combine(end_date, time.min, tzinfo=tzinfo)
    return start_dt.astimezone(ZoneInfo("UTC")), end_dt.astimezone(ZoneInfo("UTC"))
