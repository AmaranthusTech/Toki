from __future__ import annotations

import logging
import os
import time
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, time as dt_time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from jcal.features.config import (
    SEKKI24_DEGS,
    sekki_info_from_deg,
    rokuyo_from_lunar_month_day,
    lunar_month_display_name,
)
from jcal.core.astronomy import AstronomyEngine
from jcal.core.config import SolarTermConfig
from jcal.core.leap_month import PrincipalTerm  # normalize用に型だけ利用
from jcal.core.providers.skyfield_provider import SkyfieldProvider
from jcal.core.solarterms import principal_terms_between
from jcal.core.newmoon import new_moons_between

# ✅ 旧暦変換は core.lunisolar の “公式口” を使う
from jcal.core.lunisolar import (
    gregorian_to_lunar,
    gregorian_to_lunar_between,
    build_range_cache,
    LunarYMD,
)

UTC = timezone.utc

router = APIRouter(prefix="/api/v1", tags=["public"])

log = logging.getLogger("jcal.api.public")


# ============================================================
# Response Models
# ============================================================
class LunarDate(BaseModel):
    year: int
    month: int
    day: int
    is_leap: bool = Field(default=False, description="閏月なら true")


class SekkiInstant(BaseModel):
    name: str
    utc: datetime
    local: datetime


class SekkiInfo(BaseModel):
    names: List[str] = Field(default_factory=list, description="その日に属する節気名（複数の可能性あり）")
    instants: List[SekkiInstant] = Field(default_factory=list, description="節気の瞬間（UTC/ローカル）")


class DayResponse(BaseModel):
    date: date
    tz: str
    lunar: Optional[LunarDate] = None
    rokuyo: Optional[str] = None
    sekki: SekkiInfo = Field(default_factory=SekkiInfo)
    astro: Dict[str, Any] = Field(default_factory=dict)


class RangeResponse(BaseModel):
    start: date
    end: date
    tz: str
    days: List[DayResponse]


# =========================================================
# Public JSON API (function-style, HTTP-ready)
# =========================================================
ROKUYO_ORDER = ["先勝", "友引", "先負", "仏滅", "大安", "赤口"]
TOKI_EPHEMERIS_ENV = "TOKI_EPHEMERIS"
TOKI_EPHEMERIS_PATH_ENV = "TOKI_EPHEMERIS_PATH"
DEFAULT_OBSERVER_LAT = 35.681236
DEFAULT_OBSERVER_LON = 139.767125


def _normalize_rokuyo(label: Optional[str]) -> Optional[str]:
    if label is None:
        return None
    s = str(label).strip()
    return s if s in ROKUYO_ORDER else None


def _format_lunar_label(month: int, day: int, is_leap: bool) -> str:
    prefix = "閏" if is_leap else ""
    return f"{prefix}{int(month):02d}/{int(day):02d}"


def _format_lunar_month_label(month: int, is_leap: bool) -> str:
    prefix = "閏" if is_leap else ""
    return f"{prefix}{int(month):02d}"


def _parse_date_any(x: str | date) -> date:
    if isinstance(x, date):
        return x
    return _parse_iso_date(str(x))


def _resolve_ephemeris(
    ephemeris: Optional[str],
    ephemeris_path: Optional[str | Path],
) -> Tuple[str, Optional[Path]]:
    ephem = (ephemeris or "").strip()
    if not ephem:
        ephem = os.environ.get(TOKI_EPHEMERIS_ENV, "de440s.bsp").strip() or "de440s.bsp"

    path_raw: Optional[str] = None
    if isinstance(ephemeris_path, Path):
        path_raw = str(ephemeris_path)
    elif isinstance(ephemeris_path, str):
        path_raw = ephemeris_path.strip()

    if not path_raw:
        path_raw = os.environ.get(TOKI_EPHEMERIS_PATH_ENV, "").strip() or None

    if path_raw:
        p = Path(path_raw).expanduser()
        if not p.exists():
            raise HTTPException(status_code=422, detail=f"ephemeris_path not found: {p}")
        return ephem, p

    return ephem, None


def _resolve_observer(lat: Optional[float], lon: Optional[float]) -> Tuple[float, float]:
    if lat is None and lon is None:
        return DEFAULT_OBSERVER_LAT, DEFAULT_OBSERVER_LON
    if lat is None or lon is None:
        raise HTTPException(status_code=422, detail="lat and lon must be provided together")
    return float(lat), float(lon)


@lru_cache(maxsize=4)
def _provider_cached(ephemeris: str, ephemeris_path: str) -> SkyfieldProvider:
    ephem = ephemeris.strip() or None
    ep_path = Path(ephemeris_path).expanduser() if ephemeris_path else None
    return SkyfieldProvider(ephemeris=ephem, ephemeris_path=ep_path)


def _provider_for_ephemeris(
    ephemeris: Optional[str],
    ephemeris_path: Optional[Path],
) -> SkyfieldProvider:
    ephem_key = (ephemeris or "").strip()
    path_key = str(ephemeris_path) if ephemeris_path else ""
    return _provider_cached(ephem_key, path_key)


def _engine_for_ephemeris(
    ephemeris: Optional[str],
    ephemeris_path: Optional[Path],
) -> AstronomyEngine:
    provider = _provider_for_ephemeris(ephemeris, ephemeris_path)
    return AstronomyEngine(provider=provider)


def _format_iso_local(dt_utc: Optional[datetime], tzinfo: ZoneInfo) -> Optional[str]:
    if dt_utc is None:
        return None
    return dt_utc.astimezone(tzinfo).replace(microsecond=0).isoformat()


def _sunrise_sunset_for_day(
    target: date,
    *,
    tzinfo_basis: ZoneInfo,
    tzinfo_output: ZoneInfo,
    provider: SkyfieldProvider,
    latitude: float,
    longitude: float,
) -> Tuple[Optional[str], Optional[str]]:
    try:
        sunrise_utc, sunset_utc = provider.sunrise_sunset_utc_for_date(
            target,
            tzinfo_basis,
            latitude=latitude,
            longitude=longitude,
        )
    except Exception:
        log.exception(
            "sunrise/sunset calculation failed: date=%s lat=%.6f lon=%.6f",
            target,
            latitude,
            longitude,
        )
        return None, None

    return _format_iso_local(sunrise_utc, tzinfo_output), _format_iso_local(sunset_utc, tzinfo_output)


def _sekki_events_between(
    start: date,
    end: date,
    *,
    tzinfo: ZoneInfo,
    ephemeris: Optional[str],
    ephemeris_path: Optional[Path],
) -> List[dict]:
    eng = _engine_for_ephemeris(ephemeris, ephemeris_path)
    cfg = SolarTermConfig()

    # JST day-basis: include possible edges by padding
    t0 = datetime(start.year, start.month, start.day, tzinfo=UTC) - timedelta(days=2)
    t1 = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=2)

    raw = principal_terms_between(
        eng,
        t0,
        t1,
        config=cfg,
        degrees=[float(x) for x in SEKKI24_DEGS],
    )
    pts = _normalize_principal_terms(raw)

    out: List[dict] = []
    for p in pts:
        info = sekki_info_from_deg(float(p.deg))
        at_local = p.instant_utc.astimezone(tzinfo)
        day_local = at_local.date()
        if not (start <= day_local <= end):
            continue
        out.append(
            {
                "name": info.name,
                "degree": int(p.deg),
                "at_jst": at_local.isoformat(),
                "date_jst": day_local.isoformat(),
            }
        )

    out.sort(key=lambda x: x["at_jst"])
    return out


def _moon_age_days(
    cache,
    t_utc: datetime,
) -> Optional[float]:
    if cache is None or not cache.months:
        return None
    starts = cache.month_starts
    i = bisect_right(starts, t_utc) - 1
    if i < 0 or i >= len(cache.months):
        return None
    nm_utc = cache.months[i].new_moon_utc
    return (t_utc - nm_utc).total_seconds() / 86400.0


def _phase_events_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    tzinfo: ZoneInfo,
) -> List[dict]:
    # minimal: detect new moons within range
    out: List[dict] = []
    for t in new_moons_between(eng, start_utc, end_utc):
        at_local = t.astimezone(tzinfo)
        out.append(
            {
                "type": "new_moon",
                "at_jst": at_local.isoformat(),
                "date_jst": at_local.date().isoformat(),
            }
        )
    return out


def get_calendar_day(
    date_: str | date,
    *,
    tz: str = "Asia/Tokyo",
    ephemeris: Optional[str] = None,
    ephemeris_path: Optional[str | Path] = None,
    day_basis: str = "jst",
    sample_policy: str = "end",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> dict:
    if day_basis.lower() != "jst":
        raise ValueError("day_basis must be 'jst'")

    d = _parse_date_any(date_)
    tzinfo_output = _get_tzinfo(tz)
    tzinfo_basis = _get_tzinfo("Asia/Tokyo")
    ephem, ephem_path = _resolve_ephemeris(ephemeris, ephemeris_path)
    obs_lat, obs_lon = _resolve_observer(lat, lon)

    cache = build_range_cache(
        d - timedelta(days=40),
        d + timedelta(days=40),
        sample_policy=sample_policy,
        ephemeris=ephem,
        ephemeris_path=ephem_path,
    )

    l = gregorian_to_lunar(d, sample_policy=sample_policy, cache=cache)
    lunar_label = _format_lunar_label(l.month, l.day, l.is_leap)
    month_label = _format_lunar_month_label(l.month, l.is_leap)

    # rokuyo
    rokuyo = _normalize_rokuyo(rokuyo_from_lunar_month_day(int(l.month), int(l.day)))

    # sekki (events on the date)
    sekki_events = _sekki_events_between(
        d,
        d,
        tzinfo=tzinfo_basis,
        ephemeris=ephem,
        ephemeris_path=ephem_path,
    )
    sekki = None
    if sekki_events:
        sekki = {
            "primary": sekki_events[0],
            "events": sekki_events,
        }

    # astronomy
    t_jst = datetime.combine(d, dt_time(12, 0), tzinfo=tzinfo_basis)
    t_utc = t_jst.astimezone(UTC)
    age_days = _moon_age_days(cache, t_utc)

    eng = _engine_for_ephemeris(ephem, ephem_path)
    provider = _provider_for_ephemeris(ephem, ephem_path)
    phase_events = _phase_events_between(
        eng,
        datetime.combine(d, dt_time(0, 0), tzinfo=tzinfo_basis).astimezone(UTC),
        datetime.combine(d, dt_time(23, 59, 59), tzinfo=tzinfo_basis).astimezone(UTC),
        tzinfo=tzinfo_basis,
    )
    phase_event = phase_events[0] if phase_events else None

    sunrise, sunset = _sunrise_sunset_for_day(
        d,
        tzinfo_basis=tzinfo_basis,
        tzinfo_output=tzinfo_output,
        provider=provider,
        latitude=obs_lat,
        longitude=obs_lon,
    )

    return {
        "meta": {
            "tz": tz,
            "day_basis": "jst",
            "ephemeris": ephem,
        },
        "date": d.isoformat(),
        "lunisolar": {
            "year": int(l.year),
            "month": int(l.month),
            "day": int(l.day),
            "leap": bool(l.is_leap),
            "month_label": month_label,
            "label": lunar_label,
            "month_name": lunar_month_display_name(int(l.month), bool(l.is_leap)),
        },
        "rokuyo": rokuyo,
        "sekki": sekki,
        "astronomy": {
            "moon_age": None if age_days is None else round(float(age_days), 6),
            "phase_event": phase_event,
            "sunrise": sunrise,
            "sunset": sunset,
        },
    }


def get_calendar_range(
    start: str | date,
    end: str | date,
    *,
    tz: str = "Asia/Tokyo",
    ephemeris: Optional[str] = None,
    ephemeris_path: Optional[str | Path] = None,
    day_basis: str = "jst",
    sample_policy: str = "end",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> dict:
    if day_basis.lower() != "jst":
        raise ValueError("day_basis must be 'jst'")

    s = _parse_date_any(start)
    e = _parse_date_any(end)
    if e < s:
        raise ValueError("end must be >= start")

    tzinfo_output = _get_tzinfo(tz)
    tzinfo_basis = _get_tzinfo("Asia/Tokyo")
    ephem, ephem_path = _resolve_ephemeris(ephemeris, ephemeris_path)
    obs_lat, obs_lon = _resolve_observer(lat, lon)

    cache = build_range_cache(
        s - timedelta(days=40),
        e + timedelta(days=40),
        sample_policy=sample_policy,
        ephemeris=ephem,
        ephemeris_path=ephem_path,
    )

    eng = _engine_for_ephemeris(ephem, ephem_path)
    provider = _provider_for_ephemeris(ephem, ephem_path)
    events_phase = _phase_events_between(
        eng,
        datetime.combine(s, dt_time(0, 0), tzinfo=tzinfo_basis).astimezone(UTC),
        datetime.combine(e, dt_time(23, 59, 59), tzinfo=tzinfo_basis).astimezone(UTC),
        tzinfo=tzinfo_basis,
    )
    phase_by_date: Dict[str, dict] = {e["date_jst"]: e for e in events_phase}

    days: List[dict] = []
    cur = s
    while cur <= e:
        l = gregorian_to_lunar(cur, sample_policy=sample_policy, cache=cache)

        lunar_label = _format_lunar_label(l.month, l.day, l.is_leap)
        month_label = _format_lunar_month_label(l.month, l.is_leap)

        rokuyo = _normalize_rokuyo(rokuyo_from_lunar_month_day(int(l.month), int(l.day)))

        sekki_events = _sekki_events_between(
            cur,
            cur,
            tzinfo=tzinfo_basis,
            ephemeris=ephem,
            ephemeris_path=ephem_path,
        )
        sekki = None
        if sekki_events:
            sekki = {"primary": sekki_events[0], "events": sekki_events}

        t_jst = datetime.combine(cur, dt_time(12, 0), tzinfo=tzinfo_basis)
        t_utc = t_jst.astimezone(UTC)
        age_days = _moon_age_days(cache, t_utc)

        phase_event = phase_by_date.get(cur.isoformat())

        sunrise, sunset = _sunrise_sunset_for_day(
            cur,
            tzinfo_basis=tzinfo_basis,
            tzinfo_output=tzinfo_output,
            provider=provider,
            latitude=obs_lat,
            longitude=obs_lon,
        )

        days.append(
            {
                "date": cur.isoformat(),
                "lunisolar": {
                    "year": int(l.year),
                    "month": int(l.month),
                    "day": int(l.day),
                    "leap": bool(l.is_leap),
                    "month_label": month_label,
                    "label": lunar_label,
                    "month_name": lunar_month_display_name(int(l.month), bool(l.is_leap)),
                },
                "rokuyo": rokuyo,
                "sekki": sekki,
                "astronomy": {
                    "moon_age": None if age_days is None else round(float(age_days), 6),
                    "phase_event": phase_event,
                    "sunrise": sunrise,
                    "sunset": sunset,
                },
            }
        )
        cur = cur + timedelta(days=1)

    # range events (sekki + new moon)
    events_sekki = _sekki_events_between(
        s,
        e,
        tzinfo=tzinfo_basis,
        ephemeris=ephem,
        ephemeris_path=ephem_path,
    )

    return {
        "meta": {
            "tz": tz,
            "day_basis": "jst",
            "ephemeris": ephem,
        },
        "range": {"start": s.isoformat(), "end": e.isoformat()},
        "days": days,
        "events": {
            "sekki": events_sekki,
            "moon_phases": events_phase,
        },
    }


# ============================================================
# Helpers: parsing & tz
# ============================================================
def _parse_iso_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {s} (expected YYYY-MM-DD)") from e


def _get_tzinfo(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError as e:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz}") from e


# ============================================================
# Engine cache (important)
# ============================================================
@lru_cache(maxsize=1)
def _engine() -> Tuple[AstronomyEngine, SolarTermConfig]:
    """
    SkyfieldProvider は重いので、API起動中は使い回し推奨。
    """
    eng = AstronomyEngine(provider=SkyfieldProvider())
    cfg = SolarTermConfig()
    return eng, cfg


# ============================================================
# Normalize principal terms (robust)
# ============================================================
def _normalize_principal_terms(zq) -> List[PrincipalTerm]:
    """
    principal_terms_between() の戻りを PrincipalTerm の配列に揃える。
    想定:
      - [(deg, datetime), ...]
      - [PrincipalTerm, ...]
      - [{"deg":.., "instant_utc":..}, ...]
      - attribute持ちのオブジェクト
    """
    out: List[PrincipalTerm] = []
    if not zq:
        return out

    for item in zq:
        if isinstance(item, PrincipalTerm):
            out.append(item)
            continue

        if isinstance(item, (tuple, list)) and len(item) == 2:
            deg, t = item
            out.append(PrincipalTerm(deg=int(round(float(deg))) % 360, instant_utc=t))
            continue

        if isinstance(item, dict):
            deg = item.get("deg", item.get("degree", item.get("lambda")))
            t = item.get("instant_utc", item.get("t", item.get("instant")))
            if deg is None or t is None:
                raise TypeError(f"Unexpected dict principal-term shape: {item}")
            out.append(PrincipalTerm(deg=int(round(float(deg))) % 360, instant_utc=t))
            continue

        deg = getattr(item, "deg", None) or getattr(item, "degree", None)
        t = getattr(item, "instant_utc", None) or getattr(item, "t", None)
        if deg is not None and t is not None:
            out.append(PrincipalTerm(deg=int(round(float(deg))) % 360, instant_utc=t))
            continue

        raise TypeError(f"Unexpected principal-term item type: {type(item).__name__} ({item!r})")

    return out


# ============================================================
# Sekki cache: year events
# ============================================================
@dataclass(frozen=True)
class _SekkiEvent:
    name: str
    utc: datetime


@lru_cache(maxsize=16)
def _sekki_events_for_year(year: int) -> List[_SekkiEvent]:
    """
    その年に関係する節気イベントをまとめて計算してキャッシュ。
    日付境界用に前後少しパディングする。
    """
    eng, cfg = _engine()

    # 年の前後も拾えるように広めに
    t0 = datetime(year - 1, 12, 1, tzinfo=UTC)
    t1 = datetime(year + 1, 1, 31, tzinfo=UTC)

    raw = principal_terms_between(
        eng,
        t0,
        t1,
        config=cfg,
        degrees=[float(x) for x in SEKKI24_DEGS],
    )
    pts = _normalize_principal_terms(raw)

    events: List[_SekkiEvent] = []
    for p in pts:
        name = sekki_info_from_deg(float(p.deg)).name
        events.append(_SekkiEvent(name=name, utc=p.instant_utc))

    events.sort(key=lambda e: e.utc)
    return events


# ============================================================
# Core feature calcs
# ============================================================
def _sekki_for_day(target: date, tzinfo: ZoneInfo) -> SekkiInfo:
    """
    年キャッシュから、target日に該当する節気だけ拾う（軽い）
    """
    events = _sekki_events_for_year(target.year)

    names: List[str] = []
    instants: List[SekkiInstant] = []

    for e in events:
        local_dt = e.utc.astimezone(tzinfo)
        if local_dt.date() != target:
            continue

        if e.name not in names:
            names.append(e.name)
        instants.append(SekkiInstant(name=e.name, utc=e.utc, local=local_dt))

    return SekkiInfo(names=names, instants=instants)


def _lunar_and_rokuyo_from_lunarymd(l: LunarYMD) -> Tuple[LunarDate, str]:
    lunar = LunarDate(year=int(l.year), month=int(l.month), day=int(l.day), is_leap=bool(l.is_leap))
    rokuyo = rokuyo_from_lunar_month_day(lunar.month, lunar.day)
    return lunar, rokuyo


def _lunar_and_rokuyo_for_day(target: date) -> Tuple[Optional[LunarDate], Optional[str]]:
    """
    旧暦と六曜を返す。
    旧暦計算が失敗した場合は (None, None) に落とす（APIとして壊さない）。
    """
    try:
        l = gregorian_to_lunar(target)
    except Exception:
        return None, None

    lunar, rokuyo = _lunar_and_rokuyo_from_lunarymd(l)
    return lunar, rokuyo


# ============================================================
# Endpoints
# ============================================================
@router.get("/day", response_model=DayResponse)
def get_day(
    date_str: str = Query(..., alias="date", description="YYYY-MM-DD"),
    tz: str = Query("Asia/Tokyo"),
    timing: bool = Query(False, description="timingログを出す（検証用）"),
) -> DayResponse:
    d = _parse_iso_date(date_str)
    tzinfo = _get_tzinfo(tz)

    t0 = time.perf_counter()
    lunar, rokuyo = _lunar_and_rokuyo_for_day(d)
    t1 = time.perf_counter()
    sekki = _sekki_for_day(d, tzinfo)
    t2 = time.perf_counter()

    if timing:
        log.warning("timing /day date=%s tz=%s lunar=%.3fs sekki=%.3fs total=%.3fs", d, tz, t1 - t0, t2 - t1, t2 - t0)

    return DayResponse(
        date=d,
        tz=tz,
        lunar=lunar,
        rokuyo=rokuyo,
        sekki=sekki,
        astro={},
    )


@router.get("/range", response_model=RangeResponse)
def get_range(
    start_str: str = Query(..., alias="start", description="YYYY-MM-DD"),
    end_str: str = Query(..., alias="end", description="YYYY-MM-DD"),
    tz: str = Query("Asia/Tokyo"),
    limit_days: int = Query(370, ge=1, le=2000, description="最大日数（DoS対策）"),
    timing: bool = Query(False, description="timingログを出す（検証用）"),
) -> RangeResponse:
    start = _parse_iso_date(start_str)
    end = _parse_iso_date(end_str)
    if end < start:
        raise HTTPException(status_code=422, detail="end must be >= start")

    days_count = (end - start).days + 1
    if days_count > limit_days:
        raise HTTPException(status_code=422, detail=f"range too large: {days_count} days (limit_days={limit_days})")

    tzinfo = _get_tzinfo(tz)

    t0 = time.perf_counter()

    # ✅ 旧暦はまとめて変換して辞書化（キャッシュ1回で速い）
    # gregorian_to_lunar_between は [start, end) なので end+1日で渡す
    lunar_map: Dict[date, LunarYMD] = {}
    t_lunar0 = time.perf_counter()
    try:
        for d, l in gregorian_to_lunar_between(start, end + timedelta(days=1)):
            lunar_map[d] = l
    except Exception:
        lunar_map = {}
    t_lunar1 = time.perf_counter()

    days: List[DayResponse] = []
    t_loop0 = time.perf_counter()
    cur = start
    while cur <= end:
        lunar: Optional[LunarDate] = None
        rokuyo: Optional[str] = None

        l = lunar_map.get(cur)
        if l is not None:
            lunar, rokuyo = _lunar_and_rokuyo_from_lunarymd(l)
        else:
            # fallback（range cache失敗時にも単日で頑張る）
            lunar, rokuyo = _lunar_and_rokuyo_for_day(cur)

        days.append(
            DayResponse(
                date=cur,
                tz=tz,
                lunar=lunar,
                rokuyo=rokuyo,
                sekki=_sekki_for_day(cur, tzinfo),
                astro={},
            )
        )
        cur = cur + timedelta(days=1)
    t_loop1 = time.perf_counter()

    if timing:
        log.warning(
            "timing /range start=%s end=%s tz=%s days=%d lunar_map=%.3fs loop=%.3fs total=%.3fs",
            start, end, tz, days_count,
            t_lunar1 - t_lunar0,
            t_loop1 - t_loop0,
            t_loop1 - t0,
        )

    return RangeResponse(start=start, end=end, tz=tz, days=days)


# =========================================================
# New calendar JSON endpoints (stable schema)
# =========================================================
@router.get("/calendar/day")
def get_calendar_day_endpoint(
    date_str: str = Query(..., alias="date", description="YYYY-MM-DD"),
    tz: str = Query("Asia/Tokyo"),
    ephemeris: str = Query(""),
    ephemeris_path: str = Query(""),
    day_basis: str = Query("jst"),
    lat: Optional[float] = Query(None, description="observer latitude (deg)"),
    lon: Optional[float] = Query(None, description="observer longitude (deg)"),
) -> Dict[str, Any]:
    ep_path = ephemeris_path.strip() or None
    return get_calendar_day(
        date_str,
        tz=tz,
        ephemeris=ephemeris,
        ephemeris_path=ep_path,
        day_basis=day_basis,
        lat=lat,
        lon=lon,
    )


@router.get("/calendar/range")
def get_calendar_range_endpoint(
    start_str: str = Query(..., alias="start", description="YYYY-MM-DD"),
    end_str: str = Query(..., alias="end", description="YYYY-MM-DD"),
    tz: str = Query("Asia/Tokyo"),
    ephemeris: str = Query(""),
    ephemeris_path: str = Query(""),
    day_basis: str = Query("jst"),
    limit_days: int = Query(370, ge=1, le=2000, description="最大日数（DoS対策）"),
    lat: Optional[float] = Query(None, description="observer latitude (deg)"),
    lon: Optional[float] = Query(None, description="observer longitude (deg)"),
) -> Dict[str, Any]:
    start = _parse_iso_date(start_str)
    end = _parse_iso_date(end_str)
    if end < start:
        raise HTTPException(status_code=422, detail="end must be >= start")

    days_count = (end - start).days + 1
    if days_count > limit_days:
        raise HTTPException(status_code=422, detail=f"range too large: {days_count} days (limit_days={limit_days})")

    ep_path = ephemeris_path.strip() or None
    return get_calendar_range(
        start,
        end,
        tz=tz,
        ephemeris=ephemeris,
        ephemeris_path=ep_path,
        day_basis=day_basis,
        lat=lat,
        lon=lon,
    )