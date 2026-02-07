from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Sequence, List, Tuple, Optional, Union, Literal
from functools import lru_cache
import logging

from skyfield.api import Loader, wgs84
from skyfield import almanac

log = logging.getLogger(__name__)


# ----------------------------
# Frame selection
# ----------------------------
EclipticFrameName = Literal[
    "of_date_true",   # true ecliptic/equinox of date (NAO寄せの本命)
    "of_date_mean",   # mean ecliptic/equinox of date (Skyfield版で無いことがある)
    "J2000",          # ecliptic J2000
    "builtin",        # obs.ecliptic_latlon()（Skyfield既定。多くの場合J2000相当）
]


def _resolve_ecliptic_frame(name: EclipticFrameName):
    """
    Return a Skyfield frame object, or None for builtin behavior.
    Skyfield versions differ; we always provide a safe fallback.

    - of_date_true: prefer true_ecliptic_and_equinox_of_date if available,
                    else fall back to ecliptic_frame (of-date系)
    - of_date_mean: prefer mean_ecliptic_and_equinox_of_date if available,
                    else fall back to ecliptic_frame
    - J2000: ecliptic_J2000_frame
    - builtin: use obs.ecliptic_latlon() as-is
    """
    if name == "builtin":
        return None

    # Available across many Skyfield versions
    from skyfield.framelib import ecliptic_frame, ecliptic_J2000_frame

    if name == "J2000":
        return ecliptic_J2000_frame

    if name == "of_date_true":
        try:
            # exists in some Skyfield versions
            from skyfield.framelib import true_ecliptic_and_equinox_of_date  # type: ignore
            return true_ecliptic_and_equinox_of_date
        except Exception:
            # fallback: still "of date"-ish in practice
            return ecliptic_frame

    if name == "of_date_mean":
        try:
            from skyfield.framelib import mean_ecliptic_and_equinox_of_date  # type: ignore
            return mean_ecliptic_and_equinox_of_date
        except Exception:
            return ecliptic_frame

    # final fallback
    return ecliptic_frame


# ----------------------------
# Ephemeris path resolution
# ----------------------------
def _project_data_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "data"


def _default_ephemeris_path() -> Path:
    """
    Prefer de440s (longer coverage) if present; otherwise fall back to de421.
    """
    data_dir = _project_data_dir()
    p440s = data_dir / "de440s.bsp"
    p421 = data_dir / "de421.bsp"
    return p440s if p440s.exists() else p421


def _resolve_ephemeris_path(
    *,
    ephemeris_path: Optional[Path],
    ephemeris: Optional[Union[str, Path]],
) -> Path:
    """
    Resolution priority:
      1) ephemeris_path (Path) if provided
      2) ephemeris (str|Path) if provided:
         - absolute path -> use as is
         - relative path / filename -> resolve under project data dir
      3) default: prefer de440s if present else de421
    """
    if ephemeris_path is not None:
        return ephemeris_path

    if ephemeris is not None:
        p = ephemeris if isinstance(ephemeris, Path) else Path(ephemeris)
        if p.is_absolute():
            return p
        # relative -> treat as data_dir/<name>
        return _project_data_dir() / p

    return _default_ephemeris_path()


@lru_cache(maxsize=32)
def _topos_for_latlon(lat: float, lon: float):
    return wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)


@dataclass(frozen=True)
class SkyfieldProvider:
    """
    Skyfield provider with:
    - default ephemeris auto-selection (de440s > de421)
    - ecliptic frame selection for solar/lunar longitude
    """

    # Legacy-style explicit Path override (highest priority if set)
    ephemeris_path: Optional[Path] = None
    # New: explicit override by str|Path
    ephemeris: Optional[Union[str, Path]] = None

    # ★追加：黄経の参照フレーム
    # NAOに寄せるなら "of_date_true" が本命
    ecliptic_frame: EclipticFrameName = "of_date_true"

    def __post_init__(self) -> None:
        resolved = _resolve_ephemeris_path(
            ephemeris_path=self.ephemeris_path,
            ephemeris=self.ephemeris,
        )
        object.__setattr__(self, "ephemeris_path", resolved)

        if not self.ephemeris_path.exists():
            data_dir = _project_data_dir()
            candidates = [
                data_dir / "de440s.bsp",
                data_dir / "de421.bsp",
            ]
            cand_str = "\n".join(f"  - {p}" for p in candidates)
            raise FileNotFoundError(
                f"Ephemeris not found: {self.ephemeris_path}\n"
                f"Place one of the following files under {data_dir}:\n"
                f"{cand_str}\n"
                "Or pass ephemeris='de440s.bsp' / ephemeris_path=Path(...)."
            )

        loader = Loader(str(self.ephemeris_path.parent))
        eph = loader(self.ephemeris_path.name)
        ts = loader.timescale()

        object.__setattr__(self, "_loader", loader)
        object.__setattr__(self, "_eph", eph)
        object.__setattr__(self, "_ts", ts)

        # bodies cache
        object.__setattr__(self, "_earth", eph["earth"])
        object.__setattr__(self, "_sun", eph["sun"])
        object.__setattr__(self, "_moon", eph["moon"])

        # ecliptic frame object (None means builtin ecliptic_latlon)
        frame_obj = _resolve_ecliptic_frame(self.ecliptic_frame)
        object.__setattr__(self, "_ecliptic_frame_obj", frame_obj)

        # cache ephemeris time coverage (fail fast / nicer error)
        start_utc, end_utc = self._compute_ephemeris_utc_range()
        object.__setattr__(self, "_ephem_start_utc", start_utc)
        object.__setattr__(self, "_ephem_end_utc", end_utc)

    def _compute_ephemeris_utc_range(self) -> Tuple[datetime, datetime]:
        """
        Compute coverage from SPK segments.
        Skyfield throws EphemerisRangeError deep inside; we surface a clearer error earlier.
        """
        segments = getattr(self._eph, "spk", None)
        if segments is None or not getattr(segments, "segments", None):
            return (
                datetime.min.replace(tzinfo=timezone.utc),
                datetime.max.replace(tzinfo=timezone.utc),
            )

        segs = segments.segments
        start_jd = min(s.start_jd for s in segs)
        end_jd = max(s.end_jd for s in segs)

        t0 = self._ts.tt_jd(start_jd)
        t1 = self._ts.tt_jd(end_jd)
        start_utc = t0.utc_datetime().replace(tzinfo=timezone.utc)
        end_utc = t1.utc_datetime().replace(tzinfo=timezone.utc)
        return start_utc, end_utc

    # ---- time helpers ----
    def _as_utc(self, dt_utc: datetime) -> datetime:
        if dt_utc.tzinfo is None:
            raise ValueError("dt_utc must be timezone-aware")
        return dt_utc.astimezone(timezone.utc)

    def _check_ephemeris_range(self, dt_utc: datetime) -> None:
        """
        Raise a friendly error if requested datetime is outside ephemeris coverage.
        """
        dt = self._as_utc(dt_utc)
        start = self._ephem_start_utc
        end = self._ephem_end_utc

        if dt < start or dt > end:
            raise ValueError(
                "Requested datetime is outside ephemeris coverage.\n"
                f"  requested: {dt.isoformat()}\n"
                f"  ephemeris: {self.ephemeris_path}\n"
                f"  coverage : {start.isoformat()} .. {end.isoformat()}\n"
                "Hint: use de440s.bsp (place it under ./data or pass ephemeris='de440s.bsp')."
            )

    def _t(self, dt_utc: datetime):
        self._check_ephemeris_range(dt_utc)
        return self._ts.from_datetime(self._as_utc(dt_utc))

    def _t_many(self, dts_utc: Sequence[datetime]):
        if not dts_utc:
            return self._ts.from_datetimes([])

        xs = [self._as_utc(dt) for dt in dts_utc]

        # Fail fast using min/max (avoid checking every point)
        mn = min(xs)
        mx = max(xs)
        self._check_ephemeris_range(mn)
        self._check_ephemeris_range(mx)

        return self._ts.from_datetimes(xs)

    # ---- core lon calc ----
    def _lon_deg(self, body_name: str, dt_utc: datetime, *, apparent: bool) -> float:
        t = self._t(dt_utc)
        body = self._sun if body_name == "sun" else self._moon

        obs = self._earth.at(t).observe(body)
        if apparent:
            obs = obs.apparent()

        frame_obj = getattr(self, "_ecliptic_frame_obj", None)

        if frame_obj is None:
            # Skyfield builtin behavior
            _lat, lon, _dist = obs.ecliptic_latlon()
        else:
            # Explicit frame (of-date true / J2000 / etc.)
            _lat, lon, _dist = obs.frame_latlon(frame_obj)

        return float(lon.degrees % 360.0)

    def _lon_deg_many(self, body_name: str, dts_utc: Sequence[datetime], *, apparent: bool) -> List[float]:
        if not dts_utc:
            return []
        t = self._t_many(dts_utc)
        body = self._sun if body_name == "sun" else self._moon

        obs = self._earth.at(t).observe(body)
        if apparent:
            obs = obs.apparent()

        frame_obj = getattr(self, "_ecliptic_frame_obj", None)

        if frame_obj is None:
            _lat, lon, _dist = obs.ecliptic_latlon()
        else:
            _lat, lon, _dist = obs.frame_latlon(frame_obj)

        arr = lon.degrees % 360.0
        return [float(x) for x in arr]

    # ---- public API (precise / calendar-safe) ----
    def sun_ecliptic_longitude_deg(self, dt_utc: datetime) -> float:
        # apparent=True を基準（今までの設計に合わせる）
        return self._lon_deg("sun", dt_utc, apparent=True)

    def moon_ecliptic_longitude_deg(self, dt_utc: datetime) -> float:
        return self._lon_deg("moon", dt_utc, apparent=True)

    # ---- fast scalar (scan) ----
    def sun_ecliptic_longitude_deg_fast(self, dt_utc: datetime) -> float:
        return self._lon_deg("sun", dt_utc, apparent=True)

    def moon_ecliptic_longitude_deg_fast(self, dt_utc: datetime) -> float:
        return self._lon_deg("moon", dt_utc, apparent=True)

    # ---- vectorized ----
    def sun_ecliptic_longitude_deg_many(self, dts_utc: Sequence[datetime], *, apparent: bool = True) -> List[float]:
        return self._lon_deg_many("sun", dts_utc, apparent=apparent)

    def moon_ecliptic_longitude_deg_many(self, dts_utc: Sequence[datetime], *, apparent: bool = True) -> List[float]:
        return self._lon_deg_many("moon", dts_utc, apparent=apparent)

    # ---- sunrise / sunset ----
    def sunrise_sunset_utc_for_date(
        self,
        day_local: date,
        tzinfo_local: tzinfo,
        *,
        latitude: float,
        longitude: float,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        if tzinfo_local is None:
            raise ValueError("tzinfo_local must be provided")

        start_local = datetime(day_local.year, day_local.month, day_local.day, tzinfo=tzinfo_local)
        end_local = start_local + timedelta(days=1)

        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        self._check_ephemeris_range(start_utc)
        self._check_ephemeris_range(end_utc)

        topos = _topos_for_latlon(latitude, longitude)
        fn = almanac.sunrise_sunset(self._eph, topos)

        t0 = self._ts.from_datetime(start_utc)
        t1 = self._ts.from_datetime(end_utc)

        times, events = almanac.find_discrete(t0, t1, fn)

        sunrise_utc: Optional[datetime] = None
        sunset_utc: Optional[datetime] = None

        for t, ev in zip(times, events):
            dt = t.utc_datetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            if int(ev) == 1 and sunrise_utc is None:
                sunrise_utc = dt
            elif int(ev) == 0 and sunset_utc is None:
                sunset_utc = dt

        if sunrise_utc is None or sunset_utc is None:
            log.warning(
                "sunrise/sunset not found: day=%s lat=%.6f lon=%.6f start_utc=%s end_utc=%s",
                day_local,
                latitude,
                longitude,
                start_utc.isoformat(),
                end_utc.isoformat(),
            )

        return sunrise_utc, sunset_utc