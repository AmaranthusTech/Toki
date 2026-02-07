# src/jcal/core/solarterms.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Tuple, Optional

from .astronomy import AstronomyEngine, angdiff180, norm360
from .config import SolarTermConfig
from .rootfind import bracket_by_scan, brentq_datetime
from .timeutil import require_utc_range


ZHONGQI_DEGS = [0.0] + [float(x) for x in range(30, 360, 30)]
SEKKI24_DEGS = [float(d) for d in range(0, 360, 15)]  # 0,15,...,345


def _build_grid(start_utc: datetime, end_utc: datetime, step: timedelta) -> List[datetime]:
    """
    Inclusive grid: start, start+step, ..., <= end.
    """
    ts: List[datetime] = []
    t = start_utc
    while t < end_utc:
        ts.append(t)
        t = t + step
    ts.append(end_utc)
    return ts


def _brackets_from_values(
    ts: List[datetime],
    vs: List[float],
    *,
    zero_eps: float = 0.0,
) -> List[Tuple[datetime, datetime]]:
    """
    Build brackets like bracket_by_scan would:
      - If v(t)==0 -> (t,t)
      - If sign changes between consecutive points -> (t_i, t_{i+1})
    """
    out: List[Tuple[datetime, datetime]] = []
    n = len(ts)
    for i in range(n - 1):
        a, b = ts[i], ts[i + 1]
        va, vb = vs[i], vs[i + 1]

        if zero_eps > 0.0 and abs(va) <= zero_eps:
            out.append((a, a))
            continue
        if zero_eps > 0.0 and abs(vb) <= zero_eps:
            out.append((b, b))
            continue

        if va == 0.0:
            out.append((a, a))
            continue
        if vb == 0.0:
            out.append((b, b))
            continue

        if va * vb < 0.0:
            out.append((a, b))

    return out


def _fast_scan_brackets(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    target: float,
    step: timedelta,
) -> List[Tuple[datetime, datetime]]:
    """
    Fast bracketing using vectorized solar longitude (non-apparent if available).
    """
    ts = _build_grid(start_utc, end_utc, step)
    lons = eng.sun_lon_many(ts, apparent=True)   # keep consistency with g_apparent
    vs = [angdiff180(lon - target) for lon in lons]
    return _brackets_from_values(ts, vs, zero_eps=1e-6)


def _fast_local_rebracket(
    eng: AstronomyEngine,
    center: datetime,
    start_utc: datetime,
    end_utc: datetime,
    *,
    target: float,
    window: timedelta,
    step: timedelta,
) -> List[Tuple[datetime, datetime]]:
    aa = max(start_utc, center - window)
    bb = min(end_utc, center + window)
    if aa >= bb:
        return []
    return _fast_scan_brackets(eng, aa, bb, target=target, step=step)


def solar_longitude_crossings(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    target_deg: float,
    config: SolarTermConfig = SolarTermConfig(),
) -> list[datetime]:
    start_utc, end_utc = require_utc_range(start_utc, end_utc)
    target = norm360(target_deg)

    # Apparent (original behavior): used for the final root solve and verification.
    def g_apparent(t: datetime) -> float:
        return angdiff180(eng.sun_lon(t) - target)

    # 1) Fast scan to get coarse brackets with minimal expensive calls
    try:
        brackets = _fast_scan_brackets(
            eng,
            start_utc,
            end_utc,
            target=target,
            step=timedelta(hours=config.scan_step_hours),
        )
    except Exception:
        brackets = []
        
    if not brackets:
        brackets = bracket_by_scan(
            g_apparent, start_utc, end_utc, timedelta(hours=config.scan_step_hours)
        )
        
    roots: list[datetime] = []

    for a, b in brackets:
        # 2) Handle exact hit: rebracket locally (fast) to get a real interval if possible
        if a == b:
            local = _fast_local_rebracket(
                eng,
                a,
                start_utc,
                end_utc,
                target=target,
                window=timedelta(hours=config.rebracket_window_hours),
                step=timedelta(minutes=config.rebracket_step_minutes),
            )
            picked: Optional[Tuple[datetime, datetime]] = None
            for x, y in local:
                if x != y:
                    # must bracket under apparent g to preserve behavior
                    gx, gy = g_apparent(x), g_apparent(y)
                    if gx * gy <= 0.0:
                        picked = (x, y)
                        break
            if picked is None:
                # final fallback: original local bracketing (slow but rare now)
                aa = max(start_utc, a - timedelta(hours=config.rebracket_window_hours))
                bb = min(end_utc,   a + timedelta(hours=config.rebracket_window_hours))
                local2 = bracket_by_scan(
                    g_apparent, aa, bb, timedelta(minutes=config.rebracket_step_minutes)
                )
                for x, y in local2:
                    if x != y and g_apparent(x) * g_apparent(y) <= 0.0:
                        picked = (x, y)
                        break
            if picked is None:
                continue
            a, b = picked

        # 3) Nudge endpoints if they land exactly on zero (keep original semantics)
        ga = g_apparent(a)
        gb = g_apparent(b)

        if ga == 0.0 and a != b:
            a = a - timedelta(seconds=1)
            ga = g_apparent(a)
        if gb == 0.0 and a != b:
            b = b + timedelta(seconds=1)
            gb = g_apparent(b)

        if a != b and ga * gb > 0.0:
            # Bracket came from fast scan but doesn't bracket under apparent;
            # do a small slow fallback around [a,b] to recover.
            local3 = bracket_by_scan(g_apparent, a, b, timedelta(minutes=config.rebracket_step_minutes))
            picked2: Optional[Tuple[datetime, datetime]] = None
            for x, y in local3:
                if x != y and g_apparent(x) * g_apparent(y) <= 0.0:
                    picked2 = (x, y)
                    break
            if picked2 is None:
                continue
            a, b = picked2

        # 4) Root solve with apparent g (original behavior)
        r = brentq_datetime(g_apparent, a, b, tol_seconds=config.tol_seconds)

        # 5) Verify it is a true target crossing (not wrap jump) — original behavior
        err_deg = abs(angdiff180(eng.sun_lon(r.t) - target))
        if err_deg <= 0.01:
           roots.append(r.t)
        else:
           # recovery: search around the candidate root using apparent scanning
           aa = max(start_utc, r.t - timedelta(hours=24))
           bb = min(end_utc,   r.t + timedelta(hours=24))
           local = bracket_by_scan(g_apparent, aa, bb, timedelta(minutes=config.rebracket_step_minutes))
           for x, y in local:
               if x != y and g_apparent(x) * g_apparent(y) <= 0.0:
                   rr = brentq_datetime(g_apparent, x, y, tol_seconds=config.tol_seconds)
                   err2 = abs(angdiff180(eng.sun_lon(rr.t) - target))
                   if err2 <= 0.01:
                       roots.append(rr.t)
                   break

    roots.sort()
    merged: list[datetime] = []
    for t in roots:
        if not merged or (t - merged[-1]).total_seconds() > config.merge_seconds:
            merged.append(t)
    return merged


def principal_terms_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    config: SolarTermConfig = SolarTermConfig(),
    degrees: Iterable[float] = ZHONGQI_DEGS,
) -> list[tuple[float, datetime]]:
    start_utc, end_utc = require_utc_range(start_utc, end_utc)

    out: list[tuple[float, datetime]] = []
    for deg in degrees:
        ts = solar_longitude_crossings(
            eng, start_utc, end_utc, target_deg=float(deg), config=config
        )
        for t in ts:
            out.append((float(deg), t))

    out.sort(key=lambda x: x[1])
    return out


def sekki24_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    config: SolarTermConfig = SolarTermConfig(),
    degrees: Iterable[float] = SEKKI24_DEGS,
) -> list[tuple[float, datetime]]:
    """
    Enumerate 24 sekki crossings (0,15,...,345) in [start_utc, end_utc).
    Returns list[(deg, datetime_utc)].
    """
    return principal_terms_between(
        eng,
        start_utc,
        end_utc,
        config=config,
        degrees=degrees,
    )