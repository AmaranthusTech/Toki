# src/jcal/core/solstice_anchor.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from bisect import bisect_right
from typing import List, Tuple, Optional, Sequence
from zoneinfo import ZoneInfo

from .astronomy import AstronomyEngine
from .config import NewMoonConfig, SolarTermConfig, LuniSolarConfig
from .newmoon import new_moons_between
from .solarterms import solar_longitude_crossings

JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class SolsticeAnchor:
    """
    Winter-solstice anchor for lunisolar month numbering.

    span_index:
      index i such that moons[i] <= solstice_utc < moons[i+1]
      => that lunar span is month 11 (non-leap) anchor.
    """
    solstice_utc: datetime
    span_index: int
    new_moon_utc: datetime
    next_new_moon_utc: datetime
    jst_date: str


def _require_utc(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _require_utc_range(start_utc: datetime, end_utc: datetime) -> tuple[datetime, datetime]:
    s = _require_utc(start_utc, "start_utc")
    e = _require_utc(end_utc, "end_utc")
    if not (s < e):
        raise ValueError("start_utc must be < end_utc")
    return s, e


def _winter_solstice_season_window(year: int) -> tuple[datetime, datetime]:
    """
    Safe window [Dec 1, Feb 1) UTC to find 270° crossing.
    """
    a = datetime(year, 12, 1, tzinfo=timezone.utc)
    b = datetime(year + 1, 2, 1, tzinfo=timezone.utc)
    return a, b


def find_winter_solstice_utc_for_year(
    eng: AstronomyEngine,
    year: int,
    *,
    solarterm_config: SolarTermConfig = SolarTermConfig(),
) -> datetime:
    """
    Find the winter solstice (sun longitude crossing 270°) for the given year.
    Returns UTC datetime (timezone-aware).
    """
    a, b = _winter_solstice_season_window(year)
    xs = solar_longitude_crossings(eng, a, b, target_deg=270.0, config=solarterm_config)
    if not xs:
        raise RuntimeError(f"Failed to find winter solstice for year={year} in {a}..{b}")
    return sorted(xs)[0]


def build_new_moons_covering_solstices(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    newmoon_config: NewMoonConfig = NewMoonConfig(),
    lunisolar_config: LuniSolarConfig = LuniSolarConfig(),
) -> List[datetime]:
    """
    Build new-moon series with padding enough to cover solstice anchoring.
    """
    start_utc, end_utc = _require_utc_range(start_utc, end_utc)

    pad = int(lunisolar_config.series_pad_days)
    a = start_utc - timedelta(days=pad)
    b = end_utc + timedelta(days=pad)

    moons = new_moons_between(eng, a, b, config=newmoon_config)
    moons.sort()
    if len(moons) < 2:
        raise RuntimeError("Not enough new moons in padded range")
    return moons


def find_solstice_anchor_in_moons(
    moons: List[datetime],
    solstice_utc: datetime,
) -> SolsticeAnchor:
    """
    Given sorted new moons and a solstice instant, find which lunar span contains it.
    """
    solstice_utc = _require_utc(solstice_utc, "solstice_utc")
    if len(moons) < 2:
        raise ValueError("moons must have >=2 items")

    i = bisect_right(moons, solstice_utc) - 1
    if i < 0 or i + 1 >= len(moons):
        raise RuntimeError("Solstice not bracketed by new moon series; increase series_pad_days")

    nm = moons[i]
    nn = moons[i + 1]
    return SolsticeAnchor(
        solstice_utc=solstice_utc,
        span_index=i,
        new_moon_utc=nm,
        next_new_moon_utc=nn,
        jst_date=solstice_utc.astimezone(JST).date().isoformat(),
    )


def solstice_anchors_for_years(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    years: List[int],
    newmoon_config: NewMoonConfig = NewMoonConfig(),
    solarterm_config: SolarTermConfig = SolarTermConfig(),
    lunisolar_config: LuniSolarConfig = LuniSolarConfig(),
) -> Tuple[List[datetime], List[SolsticeAnchor]]:
    """
    Step2 utility (robust): see your current implementation.
    """
    start_utc, end_utc = _require_utc_range(start_utc, end_utc)
    if not years:
        raise ValueError("years must not be empty")

    base_years = sorted(set(int(y) for y in years))

    def _prev_anchor_year_for(start_dt: datetime) -> int:
        y = start_dt.year
        sol_y = find_winter_solstice_utc_for_year(eng, y, solarterm_config=solarterm_config)
        return y - 1 if start_dt < sol_y else y

    def _next_anchor_year_for(end_dt: datetime) -> int:
        y = end_dt.year
        sol_y = find_winter_solstice_utc_for_year(eng, y, solarterm_config=solarterm_config)
        return y + 1 if end_dt > sol_y else y

    extra_years: set[int] = set()
    extra_years.add(_prev_anchor_year_for(start_utc))
    extra_years.add(_next_anchor_year_for(end_utc))
    for y in base_years:
        extra_years.add(y - 1)
        extra_years.add(y + 1)

    solstice_years = sorted(set(base_years) | extra_years)

    solstices: List[Tuple[int, datetime]] = []
    for y in solstice_years:
        sol = find_winter_solstice_utc_for_year(eng, y, solarterm_config=solarterm_config)
        solstices.append((y, sol))
    solstices.sort(key=lambda x: x[1])

    if not solstices:
        return [], []

    pad0 = int(lunisolar_config.series_pad_days)
    if pad0 < 1:
        pad0 = 1

    earliest_solstice = solstices[0][1]
    latest_solstice = solstices[-1][1]
    base_a = min(start_utc, earliest_solstice)
    base_b = max(end_utc, latest_solstice)

    moons: List[datetime] = []
    last_err: Exception | None = None

    for pad_days in (pad0, max(pad0, 60), max(pad0, 90), max(pad0, 120), max(pad0, 180)):
        try:
            nm_a = base_a - timedelta(days=pad_days)
            nm_b = base_b + timedelta(days=pad_days)

            moons = new_moons_between(eng, nm_a, nm_b, config=newmoon_config)
            moons.sort()

            if len(moons) < 2:
                raise RuntimeError("Not enough new moons to bracket solstices")

            _ = [find_solstice_anchor_in_moons(moons, sol_dt) for (_yy, sol_dt) in solstices]
            break

        except Exception as e:
            last_err = e
            moons = []
            continue

    if not moons:
        raise RuntimeError(
            "Solstice not bracketed by new moon series even after expanding padding. "
            "Consider increasing lunisolar_config.series_pad_days or adjusting the range."
        ) from last_err

    anchors: List[SolsticeAnchor] = []
    for (_yy, sol_dt) in solstices:
        anchors.append(find_solstice_anchor_in_moons(moons, sol_dt))

    anchors.sort(key=lambda a: a.solstice_utc)
    return moons, anchors


def span_count_between_anchors(a: SolsticeAnchor, b: SolsticeAnchor) -> int:
    """
    Number of lunar spans between anchors:
      spans in [a.span_index, b.span_index)  => b.span_index - a.span_index
    """
    return b.span_index - a.span_index


# ============================================================
# Step3: Month count + leap-month existence decision
# ============================================================

@dataclass(frozen=True)
class SaisjitsuWindow:
    """
    A "saisjitsu" window: from month-11 anchor (winter solstice month) to next year’s month-11 anchor.

    - month_count: number of lunar months between them (start inclusive, end exclusive)
    - is_leap_year: True if month_count == 13
    """
    start_anchor: SolsticeAnchor
    end_anchor: SolsticeAnchor
    month_count: int
    is_leap_year: bool


def _pick_anchor_by_year(anchors: List[SolsticeAnchor], year: int) -> SolsticeAnchor:
    """
    Pick the SolsticeAnchor whose solstice_utc.year == year.
    Raise if not found.
    """
    for a in anchors:
        if a.solstice_utc.year == year:
            return a
    raise ValueError(f"No solstice anchor found for year={year}. Available: {[x.solstice_utc.year for x in anchors]}")


def saisjitsu_window_for_year(
    anchors: List[SolsticeAnchor],
    year: int,
) -> SaisjitsuWindow:
    """
    Step3 core:
      - Define saisjitsu window as: (winter solstice month of 'year') -> (winter solstice month of 'year+1')
      - Count months between anchors: start inclusive, end exclusive

    Returns:
      SaisjitsuWindow with (month_count, is_leap_year)
    """
    a = _pick_anchor_by_year(anchors, year)
    b = _pick_anchor_by_year(anchors, year + 1)

    # Must be chronological
    if not (a.solstice_utc < b.solstice_utc):
        raise ValueError("Anchors must be chronological: year and year+1 seem inverted")

    n = span_count_between_anchors(a, b)

    # In a lunisolar calendar this should be either 12 or 13 (rarely you may want to assert).
    if n not in (12, 13):
        raise RuntimeError(f"Unexpected month_count={n} between solstice anchors for year={year} -> {year+1}")

    return SaisjitsuWindow(
        start_anchor=a,
        end_anchor=b,
        month_count=n,
        is_leap_year=(n == 13),
    )


def saisjitsu_windows_for_years(
    anchors: List[SolsticeAnchor],
    years: List[int],
) -> List[Tuple[int, bool]]:
    """
    Convenience: build Step3 results for multiple years.
    """
    out: List[SaisjitsuWindow] = []
    for y in sorted(set(int(x) for x in years)):
        out.append(saisjitsu_window_for_year(anchors, y))
    return out

# ============================================================
# Lunar-year label helper (for printing / verification)
# ============================================================

@dataclass(frozen=True)
class LunarYearLabel:
    """
    A display-oriented label for "lunar year" of a saisjitsu window.

    lunar_year:
      Gregorian year of the Lunar New Year (month 1, non-leap) new moon in JST.
      (Example: if lunar new year happens on 2034-02-XX JST, lunar_year=2034)

    NOTE:
      To determine month-1 accurately in leap years, you MUST pass leap_span_pos
      decided by Step4. If leap_span_pos is omitted, this assumes no leap month
      before month-1 within the window (may be wrong for edge cases like leap-11/12).
    """
    saisjitsu_year: int
    lunar_year: int
    lunar_new_year_jst_date: str
    month1_span_pos: int              # 0-based position within the window
    month1_span_index: int            # global span index in moons[]
    month1_new_moon_utc: datetime
    used_leap_span_pos: Optional[int]


def _assign_month_numbers_for_window(
    span_count: int,
    *,
    leap_span_pos: Optional[int],
    anchor_month_no: int = 11,
) -> List[Tuple[int, bool]]:
    """
    Local month-number simulation (avoid circular import with leap_month.py).

    Returns list of (month_no, is_leap) for each span position.
    """
    if span_count <= 0:
        return []

    out: List[Tuple[int, bool]] = []
    cur = int(anchor_month_no)

    for pos in range(span_count):
        if pos == 0:
            out.append((cur, False))
            continue

        if leap_span_pos is not None and pos == leap_span_pos:
            out.append((cur, True))
        else:
            cur = 1 if cur == 12 else (cur + 1)
            out.append((cur, False))

    return out


def lunar_year_label_for_saisjitsu_window(
    moons: Sequence[datetime],  # ←ここ修正（Listでも動くけど堅さ優先）
    w: SaisjitsuWindow,
    *,
    saisjitsu_year: int,
    leap_span_pos: Optional[int] = None,
    anchor_month_no: int = 11,
) -> LunarYearLabel:
    """
    Compute "lunar year" label for a saisjitsu window.

    Definition used here:
      - Find the first span within the window labeled as month 1 (non-leap).
      - lunar_year is the Gregorian year (JST) of that month-1 new moon.

    Parameters:
      moons:
        The same new-moon series used to build anchors (sorted, timezone-aware).
      w:
        SaisjitsuWindow (year winter-solstice month -> year+1 winter-solstice month).
      saisjitsu_year:
        Label for the window (usually the winter-solstice year you printed).
      leap_span_pos:
        (Optional but recommended) 0-based position of the leap month within the window,
        decided by Step4. If omitted, month-1 may be wrong in cases where leap-11/12 exists.
    """
    if len(moons) < 2:
        raise ValueError("moons must have >=2 items")
    if w.month_count <= 0:
        raise ValueError("window month_count must be positive")

    # spans in this window are:
    #   global span indices [start_span_index, end_span_index)
    start_span_index = int(w.start_anchor.span_index)
    end_span_index = int(w.end_anchor.span_index)

    if end_span_index - start_span_index != int(w.month_count):
        raise ValueError(
            f"Window month_count mismatch: "
            f"end-start={end_span_index-start_span_index} vs month_count={w.month_count}"
        )

    labels = _assign_month_numbers_for_window(
        int(w.month_count),
        leap_span_pos=leap_span_pos,
        anchor_month_no=anchor_month_no,
    )

    # Find month 1 (non-leap) within the window
    month1_pos: Optional[int] = None
    for pos, (mno, is_leap) in enumerate(labels):
        if mno == 1 and (not is_leap):
            month1_pos = pos
            break

    if month1_pos is None:
        raise RuntimeError(
            f"Failed to locate month-1 (non-leap) within window year={saisjitsu_year}. "
            f"Consider passing correct leap_span_pos from Step4."
        )

    month1_span_index = start_span_index + month1_pos
    if month1_span_index < 0 or month1_span_index >= len(moons):
        raise RuntimeError("month1 span_index out of moons range; check moons coverage/padding")

    nm_utc = _require_utc(moons[month1_span_index], "moons[month1_span_index]")
    nm_jst_date = nm_utc.astimezone(JST).date().isoformat()
    lunar_year = nm_utc.astimezone(JST).year

    return LunarYearLabel(
        saisjitsu_year=int(saisjitsu_year),
        lunar_year=int(lunar_year),
        lunar_new_year_jst_date=nm_jst_date,
        month1_span_pos=int(month1_pos),
        month1_span_index=int(month1_span_index),
        month1_new_moon_utc=nm_utc,
        used_leap_span_pos=(int(leap_span_pos) if leap_span_pos is not None else None),
    )