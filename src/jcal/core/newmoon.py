# src/jcal/core/newmoon.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple

from .astronomy import AstronomyEngine, norm360, angdiff180
from .config import NewMoonConfig
from .timeutil import require_utc_range, require_utc


def _phase360(eng: AstronomyEngine, t_utc: datetime) -> float:
    """(moon - sun) mod 360 in [0, 360)."""
    return norm360(eng.moon_lon(t_utc) - eng.sun_lon(t_utc))


@dataclass(frozen=True)
class _Sample:
    t: datetime
    phase360: float
    unwrapped: float


def _unwrap(samples: List[Tuple[datetime, float]]) -> List[_Sample]:
    """
    Unwrap phase series so it becomes continuous.
    New moon corresponds to crossing 360*k (wrap point).
    """
    if not samples:
        return []

    out: List[_Sample] = []
    offset = 0.0
    prev = samples[0][1]
    out.append(_Sample(samples[0][0], prev, prev))

    for t, ph in samples[1:]:
        dp = ph - prev
        # typical wrap: 350 -> 5  => dp ~ -345
        if dp < -180.0:
            offset += 360.0
        # rare reverse wrap, keep symmetric
        elif dp > 180.0:
            offset -= 360.0
        uw = ph + offset
        out.append(_Sample(t, ph, uw))
        prev = ph

    return out


def _bisect_new_moon(
    eng: AstronomyEngine,
    a: datetime,
    b: datetime,
    *,
    tol_seconds: float,
    max_iter: int = 80,
) -> datetime:
    """
    Refine within [a,b] using continuous near-0 function.
    We ONLY call this on brackets created by wrap-crossing detection,
    so the root is near phase=0 (not near +/-180 discontinuity).
    """
    a = require_utc(a, "a")
    b = require_utc(b, "b")

    lo, hi = a, b
    for _ in range(max_iter):
        mid = lo + (hi - lo) / 2

        # signed distance to 0 in (-180,180]
        flo = angdiff180(_phase360(eng, lo))
        fmid = angdiff180(_phase360(eng, mid))

        if abs((hi - lo).total_seconds()) <= tol_seconds:
            return mid

        # normal bisection when sign changes
        if flo == 0.0:
            return lo
        if fmid == 0.0:
            return mid

        # choose side that contains the sign flip relative to flo
        if flo * fmid <= 0:
            hi = mid
        else:
            lo = mid

    return lo + (hi - lo) / 2


def new_moons_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    config: NewMoonConfig | None = None,
) -> List[datetime]:
    """
    Robust new moon instants in [start_utc, end_utc).
    Prevents false detections at full moon.
    """
    start_utc, end_utc = require_utc_range(start_utc, end_utc)
    if config is None:
        config = NewMoonConfig()

    step = timedelta(hours=float(config.scan_step_hours))
    tol = float(config.tol_seconds)

    # coarse sampling
    raw: List[Tuple[datetime, float]] = []
    t = start_utc
    while t <= end_utc:
        raw.append((t, _phase360(eng, t)))
        t += step

    us = _unwrap(raw)
    if len(us) < 2:
        return []

    out: List[datetime] = []
    for i in range(len(us) - 1):
        s0, s1 = us[i], us[i + 1]
        k0 = int(s0.unwrapped // 360.0)
        k1 = int(s1.unwrapped // 360.0)

        # crossed 360*k boundary => new moon bracket
        if k1 > k0:
            nm = _bisect_new_moon(eng, s0.t, s1.t, tol_seconds=tol)

            # sanity filter: must be VERY close to 0°
            ph = _phase360(eng, nm)
            dist0 = min(ph, 360.0 - ph)
            if dist0 > 1e-2:  # 0.01 deg ~ 36 arcsec: extremely strict
                # if you want, you can loosen to 0.05 deg etc
                continue

            if start_utc <= nm < end_utc:
                out.append(nm)

    return out