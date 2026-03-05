from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from zoneinfo import ZoneInfo

from skyfield import almanac
from skyfield.api import load


@dataclass(frozen=True)
class SolsticeRequest:
    year: int
    degree: float
    tz: str
    ephemeris_path: str


@dataclass(frozen=True)
class SolsticeEvent:
    utc: str
    jst: str
    jst_date: str


@dataclass(frozen=True)
class SolsticeResult:
    year: int
    degree: float
    tz: str
    ephemeris_path: str
    events: list[SolsticeEvent]
    status: str
    note: str | None = None


class SolarTermCalculator:
    def find_event(self, req: SolsticeRequest) -> SolsticeResult:
        raise NotImplementedError


class NotImplementedSolarTermCalculator(SolarTermCalculator):
    def find_event(self, req: SolsticeRequest) -> SolsticeResult:
        return SolsticeResult(
            year=req.year,
            degree=req.degree,
            tz=req.tz,
            ephemeris_path=req.ephemeris_path,
            events=[],
            status="not_implemented",
            note="TODO: implement astronomical calculation backend",
        )


class SkyfieldSolarTermCalculator(SolarTermCalculator):
    _DEGREE_TO_SEASON_INDEX = {
        0: 0,
        90: 1,
        180: 2,
        270: 3,
    }

    def find_event(self, req: SolsticeRequest) -> SolsticeResult:
        rounded_degree = int(round(req.degree))
        season_index = self._DEGREE_TO_SEASON_INDEX.get(rounded_degree)
        if season_index is None:
            return SolsticeResult(
                year=req.year,
                degree=req.degree,
                tz=req.tz,
                ephemeris_path=req.ephemeris_path,
                events=[],
                status="unsupported_degree",
                note="supported degrees: 0, 90, 180, 270",
            )

        ts = load.timescale()
        eph = load(req.ephemeris_path)
        t0 = ts.utc(req.year, 1, 1)
        t1 = ts.utc(req.year + 1, 1, 1)

        season_fn = almanac.seasons(eph)
        times, seasons = almanac.find_discrete(t0, t1, season_fn)

        tzinfo = ZoneInfo(req.tz)
        events: list[SolsticeEvent] = []
        for t, season in zip(times, seasons):
            if int(season) != season_index:
                continue
            utc_dt = t.utc_datetime()
            if utc_dt.tzinfo is None:
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
            jst_dt = utc_dt.astimezone(tzinfo)
            events.append(
                SolsticeEvent(
                    utc=utc_dt.isoformat(),
                    jst=jst_dt.isoformat(),
                    jst_date=jst_dt.date().isoformat(),
                )
            )

        return SolsticeResult(
            year=req.year,
            degree=req.degree,
            tz=req.tz,
            ephemeris_path=req.ephemeris_path,
            events=events,
            status="ok",
        )
