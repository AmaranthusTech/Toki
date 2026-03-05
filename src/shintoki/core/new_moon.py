from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from skyfield import almanac
from skyfield.api import load


@dataclass(frozen=True)
class NewMoonWindowRequest:
    tz: str
    ephemeris_path: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class NewMoonEvent:
    utc: str
    local: str
    local_date: str


class NewMoonCalculator:
    def find_new_moons_between(self, req: NewMoonWindowRequest) -> list[NewMoonEvent]:
        raise NotImplementedError


class SkyfieldNewMoonCalculator(NewMoonCalculator):
    def find_new_moons_between(self, req: NewMoonWindowRequest) -> list[NewMoonEvent]:
        ts = load.timescale()
        eph = load(req.ephemeris_path)

        start_utc = req.start_utc.astimezone(timezone.utc)
        end_utc = req.end_utc.astimezone(timezone.utc)
        t0 = ts.from_datetime(start_utc)
        t1 = ts.from_datetime(end_utc)
        times, phases = almanac.find_discrete(t0, t1, almanac.moon_phases(eph))

        tzinfo = ZoneInfo(req.tz)
        events: list[NewMoonEvent] = []
        for t, phase in zip(times, phases):
            if int(phase) != 0:
                continue
            utc_dt = t.utc_datetime()
            if utc_dt.tzinfo is None:
                utc_dt = utc_dt.replace(tzinfo=timezone.utc)
            local_dt = utc_dt.astimezone(tzinfo)
            events.append(
                NewMoonEvent(
                    utc=utc_dt.isoformat(),
                    local=local_dt.isoformat(),
                    local_date=local_dt.date().isoformat(),
                )
            )
        return events


def year_window_utc(year: int, pad_days: int) -> tuple[datetime, datetime]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc) - timedelta(days=pad_days)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) + timedelta(days=pad_days)
    return start, end
