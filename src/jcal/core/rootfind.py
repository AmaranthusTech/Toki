# src/jcal/core/rootfind.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Tuple
import math


@dataclass(frozen=True)
class RootResult:
    t: datetime
    iterations: int


def bracket_by_scan(
    f: Callable[[datetime], float],
    start: datetime,
    end: datetime,
    step: timedelta,
) -> List[Tuple[datetime, datetime]]:
    """
    Scan [start, end] by fixed step and return candidate brackets.

    Returns list of (a, b) such that:
      - sign change: f(a) * f(b) < 0  -> (a, b)
      - exact hit at an endpoint:
            f(a) == 0  -> (a, a)
            f(b) == 0  -> (b, b)   (intentional; caller may treat (a==b) specially)

    Notes
    -----
    - Evaluates `end` inclusively exactly once.
    - NaN/inf in a segment: that segment is skipped, but scanning continues.
    """
    if step.total_seconds() <= 0:
        raise ValueError("step must be positive")
    if not (start < end):
        return []

    out: List[Tuple[datetime, datetime]] = []

    t_prev = start
    f_prev = f(t_prev)
    if not math.isfinite(f_prev):
        # We still try to move forward until we find a finite point.
        f_prev = float("nan")

    t = start
    while True:
        t = t + step
        if t >= end:
            t = end

        f_cur = f(t)
        if not math.isfinite(f_cur):
            # skip this segment; move on
            t_prev, f_prev = t, f_cur
            if t == end:
                break
            continue

        # If previous is invalid, reset baseline
        if not math.isfinite(f_prev):
            t_prev, f_prev = t, f_cur
            if t == end:
                break
            continue

        # endpoint hits
        if f_prev == 0.0:
            out.append((t_prev, t_prev))
        elif f_cur == 0.0:
            out.append((t, t))
        # sign change
        elif f_prev * f_cur < 0.0:
            out.append((t_prev, t))

        t_prev, f_prev = t, f_cur
        if t == end:
            break

    return out


def brentq_datetime(
    f: Callable[[datetime], float],
    a: datetime,
    b: datetime,
    tol_seconds: float = 0.5,
    max_iter: int = 100,
) -> RootResult:
    """
    Robust root-finding on datetime bracket [a,b] where f(a)*f(b) <= 0.

    This implementation is intentionally conservative:
      - maintains a valid bracket at all times
      - uses bisection as the backbone (guaranteed convergence)
      - optionally tries a secant step when it stays inside the bracket

    This avoids edge-case failures that can happen with buggy/fragile Brent swaps.

    Returns
    -------
    RootResult(t, iterations)
      t: timezone-aware datetime (same tzinfo as inputs)
    """
    if tol_seconds <= 0:
        raise ValueError("tol_seconds must be positive")
    if a > b:
        a, b = b, a

    fa = f(a)
    fb = f(b)

    if not (math.isfinite(fa) and math.isfinite(fb)):
        raise ValueError("Non-finite function value at bracket endpoints.")
    if fa == 0.0:
        return RootResult(a, 0)
    if fb == 0.0:
        return RootResult(b, 0)
    if fa * fb > 0.0:
        raise ValueError("Root is not bracketed (same sign).")

    # Work in seconds from a0 for numeric stability
    a0 = a

    def x(dt: datetime) -> float:
        return (dt - a0).total_seconds()

    def dt(sec: float) -> datetime:
        return a0 + timedelta(seconds=sec)

    xa = x(a)
    xb = x(b)

    # Main loop: bracketed hybrid (secant-inside else bisection)
    for it in range(1, max_iter + 1):
        # stop if interval small enough
        if (xb - xa) <= tol_seconds:
            mid = 0.5 * (xa + xb)
            return RootResult(dt(mid), it)

        # candidate by secant (false position)
        cand_sec = None
        if fb != fa:
            xs = xb - fb * (xb - xa) / (fb - fa)
            # must stay strictly inside bracket to be useful
            if xa < xs < xb and math.isfinite(xs):
                cand_sec = xs

        # fallback: bisection
        xm = 0.5 * (xa + xb)

        # choose candidate
        xc = cand_sec if cand_sec is not None else xm
        tc = dt(xc)
        fc = f(tc)

        # if non-finite, fallback to bisection point
        if not math.isfinite(fc):
            xc = xm
            tc = dt(xc)
            fc = f(tc)
            if not math.isfinite(fc):
                # cannot proceed safely
                raise ValueError("Non-finite function value during root finding.")

        # exact hit
        if fc == 0.0:
            return RootResult(tc, it)

        # update bracket (keep sign change)
        if fa * fc < 0.0:
            xb, fb = xc, fc
        else:
            xa, fa = xc, fc

    # If max_iter reached, return midpoint as best effort
    mid = 0.5 * (xa + xb)
    return RootResult(dt(mid), max_iter)