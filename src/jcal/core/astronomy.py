# src/jcal/core/astronomy.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence, List, runtime_checkable, Any


def norm360(deg: float) -> float:
    x = deg % 360.0
    return x + 360.0 if x < 0 else x


def angdiff180(deg: float) -> float:
    """Map angle to (-180, 180]."""
    x = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if x == -180.0 else x


@runtime_checkable
class AstroProvider(Protocol):
    # baseline (existing)
    def sun_ecliptic_longitude_deg(self, dt_utc: datetime) -> float: ...
    def moon_ecliptic_longitude_deg(self, dt_utc: datetime) -> float: ...

    # optional fast scalar
    def sun_ecliptic_longitude_deg_fast(self, dt_utc: datetime) -> float: ...
    def moon_ecliptic_longitude_deg_fast(self, dt_utc: datetime) -> float: ...

    # optional vectorized batch
    def sun_ecliptic_longitude_deg_many(self, dts_utc: Sequence[datetime], *, apparent: bool = True) -> List[float]: ...
    def moon_ecliptic_longitude_deg_many(self, dts_utc: Sequence[datetime], *, apparent: bool = True) -> List[float]: ...


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC/JST etc).")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class AstronomyEngine:
    provider: AstroProvider

    def sun_lon(self, dt_utc: datetime) -> float:
        """Return apparent solar ecliptic longitude (degrees) at dt_utc (timezone-aware UTC)."""
        return norm360(self.provider.sun_ecliptic_longitude_deg(_as_utc(dt_utc)))

    def moon_lon(self, dt_utc: datetime) -> float:
        """Return apparent lunar ecliptic longitude (degrees) at dt_utc (timezone-aware UTC)."""
        return norm360(self.provider.moon_ecliptic_longitude_deg(_as_utc(dt_utc)))

    def sun_lon_fast(self, dt_utc: datetime) -> float:
        """
        Fast solar longitude if provider supports it; otherwise fall back to apparent.
        Intended for scanning/bracketing where speed matters.
        """
        dt = _as_utc(dt_utc)
        f = getattr(self.provider, "sun_ecliptic_longitude_deg_fast", None)
        if callable(f):
            return norm360(f(dt))
        return self.sun_lon(dt)

    def moon_lon_fast(self, dt_utc: datetime) -> float:
        dt = _as_utc(dt_utc)
        f = getattr(self.provider, "moon_ecliptic_longitude_deg_fast", None)
        if callable(f):
            return norm360(f(dt))
        return self.moon_lon(dt)

    def sun_lon_many(self, dts_utc: Sequence[datetime], *, apparent: bool = True) -> List[float]:
        """
        Vectorized solar longitude if provider supports it; otherwise fall back to loop.
        """
        if not dts_utc:
            return []
        dts = [_as_utc(dt) for dt in dts_utc]
        f = getattr(self.provider, "sun_ecliptic_longitude_deg_many", None)
        if callable(f):
            xs = f(dts, apparent=apparent)
            return [norm360(float(v)) for v in xs]
        # fallback scalar
        if apparent:
            return [self.sun_lon(dt) for dt in dts]
        return [self.sun_lon_fast(dt) for dt in dts]

    def moon_lon_many(self, dts_utc: Sequence[datetime], *, apparent: bool = True) -> List[float]:
        if not dts_utc:
            return []
        dts = [_as_utc(dt) for dt in dts_utc]
        f = getattr(self.provider, "moon_ecliptic_longitude_deg_many", None)
        if callable(f):
            xs = f(dts, apparent=apparent)
            return [norm360(float(v)) for v in xs]
        if apparent:
            return [self.moon_lon(dt) for dt in dts]
        return [self.moon_lon_fast(dt) for dt in dts]

    def moon_sun_lon_diff(self, dt_utc: datetime) -> float:
        """Δλ = λ☾ - λ☉ mapped to (-180, 180]. New moon ≈ 0."""
        d = self.moon_lon(dt_utc) - self.sun_lon(dt_utc)
        return angdiff180(d)