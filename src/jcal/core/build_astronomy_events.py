# src/jcal/core/build_astronomy_events.py
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Tuple, Optional, Union
from zoneinfo import ZoneInfo

# ---- your project imports ----
from .astronomy import AstronomyEngine
from .config import NewMoonConfig
from .newmoon import new_moons_between  # ★これを使う
from .providers.skyfield_provider import SkyfieldProvider

JST = ZoneInfo("Asia/Tokyo")


# ============================================================
# Angle helpers
# ============================================================

def norm360(deg: float) -> float:
    """Normalize to [0, 360)."""
    x = deg % 360.0
    return x + 360.0 if x < 0 else x


def angdiff180(deg: float) -> float:
    """Map angle to (-180, 180]. Useful for root finding around 0."""
    x = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if x == -180.0 else x


def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(timezone.utc)


def jst_date_of(dt_utc: datetime) -> str:
    return dt_utc.astimezone(JST).date().isoformat()


# ============================================================
# Root finding (bisection on monotone-ish small intervals)
# ============================================================

def bisect_root(
    f,
    a: datetime,
    b: datetime,
    *,
    max_iter: int = 80,
    tol_seconds: float = 1.0,
) -> datetime:
    """
    Find t in [a,b] such that f(t)=0 using bisection, assuming sign change.
    Return UTC-aware datetime.
    """
    a = utc(a)
    b = utc(b)
    fa = float(f(a))
    fb = float(f(b))

    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0:
        raise ValueError("bisect_root requires sign change interval")

    for _ in range(max_iter):
        mid = a + (b - a) / 2
        fm = float(f(mid))

        # stop by time width
        if (b - a).total_seconds() <= tol_seconds:
            return utc(mid)

        # classic bisection
        if fa * fm <= 0:
            b = mid
            fb = fm
        else:
            a = mid
            fa = fm

    return utc(a + (b - a) / 2)


# ============================================================
# Event models
# ============================================================

@dataclass(frozen=True)
class NewMoonEvent:
    t_utc: datetime
    jst_date: str


@dataclass(frozen=True)
class PrincipalTermEvent:
    deg: int              # 30,60,...,330
    instant_utc: datetime
    jst_date: str


# ============================================================
# Core computations
# ============================================================

def moon_sun_lon_diff(eng: AstronomyEngine, t_utc: datetime) -> float:
    """
    Δλ = λ_moon - λ_sun mapped to (-180,180].
    New moon occurs near 0.
    """
    d = eng.moon_lon(t_utc) - eng.sun_lon(t_utc)
    return angdiff180(d)


def find_new_moons_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    scan_step_hours: float = 6,
    tol_seconds: float = 1,
) -> List[NewMoonEvent]:
    """
    CLI 用：朔（新月）だけを抽出する。
    実装は core/newmoon.py の new_moons_between に一本化する（満月混入を根絶）。
    """
    cfg = NewMoonConfig(scan_step_hours=scan_step_hours, tol_seconds=tol_seconds)
    xs = new_moons_between(eng, start_utc, end_utc, config=cfg)

    out: List[NewMoonEvent] = []
    for t in xs:
        out.append(NewMoonEvent(t_utc=t, jst_date=str(t.astimezone(JST).date())))
    return out


def sun_lon_minus_target(eng: AstronomyEngine, t_utc: datetime, target_deg: float) -> float:
    """
    f(t) = wrap180(sun_lon(t) - target_deg)
    Root at crossing. Using wrap to (-180,180] avoids 0/360 jump issues.
    """
    return angdiff180(eng.sun_lon(t_utc) - target_deg)


def _unwrap_deg(raw_deg: float, ref_unwrapped: float) -> float:
    """
    raw_deg in [0,360)
    ref_unwrapped is continuous degree (can be outside 0..360)
    Return unwrapped degree close to ref_unwrapped (within +/-180).
    """
    ref_mod = ref_unwrapped % 360.0
    delta = angdiff180(raw_deg - ref_mod)  # (-180,180]
    return ref_unwrapped + delta


def find_principal_terms_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    degrees: Iterable[int] = tuple(range(0, 360, 30)),  # 0,30,...,330
    scan_step: timedelta = timedelta(hours=6),
    refine_tol_seconds: float = 1.0,
) -> List[PrincipalTermEvent]:
    """
    Detect principal-term instants (中気) in [start_utc, end_utc) for 30° multiples.

    Robust policy:
      - Track sun longitude as a continuous (unwrapped) value.
      - In each [t0,t1], detect which 30° grid points are crossed.
      - Refine each crossing by bisection on unwrapped_lon(t) - target_unwrapped.
    """
    start_utc = utc(start_utc)
    end_utc = utc(end_utc)
    if not (start_utc < end_utc):
        return []

    deg_set = set(int(d) for d in degrees)
    out: List[PrincipalTermEvent] = []

    # initial
    t0 = start_utc
    lon0_raw = norm360(eng.sun_lon(t0))
    lon0_u = float(lon0_raw)  # start unwrapped baseline at raw value

    t1 = t0 + scan_step
    while t1 <= end_utc:
        lon1_raw = norm360(eng.sun_lon(t1))
        lon1_u = _unwrap_deg(float(lon1_raw), lon0_u)

        # ensure forward progress (sun lon should increase)
        if lon1_u < lon0_u:
            lon1_u += 360.0

        # find all 30° grid crossings in (lon0_u, lon1_u]
        eps = 1e-12
        next_grid = (int((lon0_u + eps) // 30) + 1) * 30

        while next_grid <= lon1_u + 1e-9:
            target_mod = int(next_grid % 360)

            if target_mod in deg_set:
                target_u = float(next_grid)

                def f(t: datetime) -> float:
                    raw = norm360(eng.sun_lon(t))
                    u = _unwrap_deg(float(raw), lon0_u)
                    if u < lon0_u:
                        u += 360.0
                    return u - target_u

                fa = f(t0)
                fb = f(t1)
                if fa == 0.0:
                    tt = t0
                elif fb == 0.0:
                    tt = t1
                elif fa * fb > 0:
                    mid = t0 + (t1 - t0) / 2
                    fm = f(mid)
                    if fa * fm <= 0:
                        tt = bisect_root(f, t0, mid, tol_seconds=refine_tol_seconds)
                    elif fm * fb <= 0:
                        tt = bisect_root(f, mid, t1, tol_seconds=refine_tol_seconds)
                    else:
                        next_grid += 30
                        continue
                else:
                    tt = bisect_root(f, t0, t1, tol_seconds=refine_tol_seconds)

                out.append(
                    PrincipalTermEvent(
                        deg=target_mod,
                        instant_utc=utc(tt),
                        jst_date=jst_date_of(utc(tt)),
                    )
                )

            next_grid += 30

        t0 = t1
        lon0_u = lon1_u
        t1 = t1 + scan_step

    out_sorted = sorted(out, key=lambda e: (e.instant_utc, e.deg))
    dedup: List[PrincipalTermEvent] = []
    last: Tuple[int, int] | None = None
    for e in out_sorted:
        key = (int(e.instant_utc.timestamp()), e.deg)
        if key != last:
            dedup.append(e)
            last = key
    return dedup


# ============================================================
# CLI
# ============================================================

def parse_iso_utc(s: str) -> datetime:
    """
    Parse ISO string. If no timezone, assume UTC.
    Examples:
      2030-01-01
      2030-01-01T00:00:00
      2030-01-01T00:00:00+00:00
    """
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_ephemeris_arg(s: Optional[str]) -> Optional[Union[str, Path]]:
    if not s:
        return None
    # allow "de440s" shorthand
    if s in ("de440s", "de421"):
        return f"{s}.bsp"
    return s


def main() -> int:
    p = argparse.ArgumentParser(
        description="Build astronomy events: new moons and principal terms (zhongqi) with JST date attribution."
    )
    p.add_argument("--start", required=True, help="Start datetime (ISO). If date-only, assumed 00:00:00Z.")
    p.add_argument("--end", required=True, help="End datetime (ISO). Exclusive.")
    p.add_argument("--scan-step-hours", type=int, default=6, help="Coarse scan step hours.")
    p.add_argument("--tol-seconds", type=float, default=1.0, help="Bisection tolerance seconds.")
    p.add_argument("--print", action="store_true", help="Print results to stdout.")

    # NEW: ephemeris selection
    p.add_argument(
        "--ephemeris",
        default=None,
        help="Ephemeris file name under ./data (e.g. de440s.bsp, de421.bsp) or shorthand (de440s/de421).",
    )
    p.add_argument(
        "--ephemeris-path",
        default=None,
        help="Explicit ephemeris path. Overrides --ephemeris if provided.",
    )

    args = p.parse_args()

    start_utc = parse_iso_utc(args.start)
    end_utc = parse_iso_utc(args.end)

    tol_seconds = float(args.tol_seconds)

    ephemeris = _parse_ephemeris_arg(args.ephemeris)
    ephemeris_path = Path(args.ephemeris_path).expanduser() if args.ephemeris_path else None

    provider = SkyfieldProvider(ephemeris=ephemeris, ephemeris_path=ephemeris_path)
    eng = AstronomyEngine(provider=provider)

    newmoons = find_new_moons_between(
        eng,
        start_utc,
        end_utc,
        scan_step_hours=args.scan_step_hours,
        tol_seconds=tol_seconds,
    )

    terms = find_principal_terms_between(
        eng,
        start_utc,
        end_utc,
        degrees=tuple(range(0, 360, 30)),
        scan_step=timedelta(hours=int(args.scan_step_hours)),
        refine_tol_seconds=tol_seconds,
    )

    if args.print:
        print("=== New Moons (朔) ===")
        for e in newmoons:
            print(f"{e.t_utc.isoformat()}  JST_date={e.jst_date}")

        print("\n=== Principal Terms (中気: 30° multiples) ===")
        for e in terms:
            print(f"{e.instant_utc.isoformat()}  deg={e.deg:03d}  JST_date={e.jst_date}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())