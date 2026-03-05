from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo

from skyfield.api import load


@dataclass(frozen=True)
class PrincipalTermRequest:
    year: int
    degree: int
    tz: str
    ephemeris_path: str


@dataclass(frozen=True)
class PrincipalTermWindowRequest:
    degree: int
    tz: str
    ephemeris_path: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class PrincipalTermEvent:
    utc: str
    jst: str
    local: str
    local_date: str


@dataclass(frozen=True)
class PrincipalTermResult:
    year: int
    degree: int
    tz: str
    ephemeris_path: str
    events: list[PrincipalTermEvent]
    status: str
    note: str | None = None


class PrincipalTermCalculator:
    def find_events(self, req: PrincipalTermRequest) -> PrincipalTermResult:
        raise NotImplementedError


class SkyfieldPrincipalTermCalculator(PrincipalTermCalculator):
    def find_events(self, req: PrincipalTermRequest) -> PrincipalTermResult:
        start_utc = datetime(req.year, 1, 1, tzinfo=timezone.utc)
        end_utc = datetime(req.year + 1, 1, 1, tzinfo=timezone.utc)
        window_req = PrincipalTermWindowRequest(
            degree=req.degree,
            tz=req.tz,
            ephemeris_path=req.ephemeris_path,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        events = self.find_events_between(window_req)
        return PrincipalTermResult(
            year=req.year,
            degree=req.degree,
            tz=req.tz,
            ephemeris_path=req.ephemeris_path,
            events=events,
            status="ok",
        )

    def find_events_between(self, req: PrincipalTermWindowRequest) -> list[PrincipalTermEvent]:
        ts = load.timescale()
        eph = load(req.ephemeris_path)
        earth = eph["earth"]
        sun = eph["sun"]

        start_utc = req.start_utc.astimezone(timezone.utc)
        end_utc = req.end_utc.astimezone(timezone.utc)
        t0 = ts.from_datetime(start_utc)
        t1 = ts.from_datetime(end_utc)
        roots = self._find_roots(ts, earth, sun, req.degree, t0.tt, t1.tt)

        tzinfo = ZoneInfo(req.tz)
        jst_tz = ZoneInfo("Asia/Tokyo")
        events: list[PrincipalTermEvent] = []
        for t in roots:
            utc_dt = t.utc_datetime()
            if utc_dt.tzinfo is None:
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
            local_dt = utc_dt.astimezone(tzinfo)
            jst_dt = utc_dt.astimezone(jst_tz)
            events.append(
                PrincipalTermEvent(
                    utc=utc_dt.isoformat(),
                    jst=jst_dt.isoformat(),
                    local=local_dt.isoformat(),
                    local_date=local_dt.date().isoformat(),
                )
            )
        return events

    def _find_roots(self, ts, earth, sun, degree: int, tt_start: float, tt_end: float):
        step_days = 1.0
        n_steps = max(2, int(math.ceil((tt_end - tt_start) / step_days)) + 1)
        tt_points = [min(tt_start + i * step_days, tt_end) for i in range(n_steps)]
        if tt_points[-1] < tt_end:
            tt_points.append(tt_end)

        unwrapped = self._sample_unwrapped_longitudes(ts, earth, sun, tt_points)
        start_u = unwrapped[0]
        end_u = unwrapped[-1]

        roots: list = []
        k_start = int(math.floor((start_u - degree) / 360.0)) - 1
        k_end = int(math.ceil((end_u - degree) / 360.0)) + 1

        for k in range(k_start, k_end + 1):
            target = degree + 360.0 * k
            if not (start_u <= target < end_u):
                continue
            bracket = self._find_bracket(tt_points, unwrapped, target)
            if bracket is None:
                continue
            tt_lo, tt_hi = bracket
            root = self._bisect_root(ts, earth, sun, target, tt_lo, tt_hi)
            if tt_start <= root.tt < tt_end:
                roots.append(root)

        roots.sort(key=lambda t: t.tt)
        return roots

    def _bisect_root(self, ts, earth, sun, target: float, tt_lo: float, tt_hi: float):
        t_lo = ts.tt_jd(tt_lo)
        t_hi = ts.tt_jd(tt_hi)
        f_lo = self._delta_to_target(earth, sun, t_lo, target)
        f_hi = self._delta_to_target(earth, sun, t_hi, target)

        if f_lo == 0.0:
            return t_lo
        if f_hi == 0.0:
            return t_hi
        if f_lo * f_hi > 0.0:
            return t_lo

        for _ in range(80):
            tt_mid = (tt_lo + tt_hi) / 2.0
            t_mid = ts.tt_jd(tt_mid)
            f_mid = self._delta_to_target(earth, sun, t_mid, target)
            if abs(f_mid) < 1e-10 or abs(tt_hi - tt_lo) < 1e-10:
                return t_mid
            if f_lo * f_mid <= 0.0:
                tt_hi = tt_mid
            else:
                tt_lo = tt_mid
                f_lo = f_mid

        return ts.tt_jd((tt_lo + tt_hi) / 2.0)

    @staticmethod
    def _sample_unwrapped_longitudes(ts, earth, sun, tt_points: list[float]) -> list[float]:
        unwrapped: list[float] = []
        prev_raw: float | None = None
        prev_unwrapped: float | None = None
        for tt in tt_points:
            t = ts.tt_jd(tt)
            raw = SkyfieldPrincipalTermCalculator._raw_longitude(earth, sun, t)
            if prev_raw is None:
                current = raw
            else:
                delta = raw - prev_raw
                if delta < -180.0:
                    delta += 360.0
                elif delta > 180.0:
                    delta -= 360.0
                current = prev_unwrapped + delta
            unwrapped.append(current)
            prev_raw = raw
            prev_unwrapped = current
        return unwrapped

    @staticmethod
    def _find_bracket(tt_points: list[float], unwrapped: list[float], target: float):
        for idx in range(len(tt_points) - 1):
            a = unwrapped[idx]
            b = unwrapped[idx + 1]
            if (a - target) == 0.0:
                return tt_points[idx], tt_points[idx]
            if (a - target) * (b - target) <= 0.0:
                return tt_points[idx], tt_points[idx + 1]
        return None

    @staticmethod
    def _raw_longitude(earth, sun, t) -> float:
        apparent = earth.at(t).observe(sun).apparent()
        _, lon, _ = apparent.ecliptic_latlon()
        return lon.degrees

    @staticmethod
    def _delta_to_target(earth, sun, t, target: float) -> float:
        value = SkyfieldPrincipalTermCalculator._raw_longitude(earth, sun, t)
        return ((value - target + 180.0) % 360.0) - 180.0
