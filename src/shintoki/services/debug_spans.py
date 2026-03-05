from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from shintoki.core.new_moon import NewMoonCalculator, NewMoonWindowRequest, year_window_utc
from shintoki.core.solar_terms import (
    PrincipalTermEvent,
    PrincipalTermWindowRequest,
    SkyfieldPrincipalTermCalculator,
)


@dataclass(frozen=True)
class SpanTermEvent:
    deg: int
    utc: str
    local: str
    local_date: str


@dataclass(frozen=True)
class MoonSpan:
    index: int
    start_utc: str
    end_utc: str
    start_local_date: str
    end_local_date_exclusive: str
    zhongqi_count: int
    zhongqi_degrees: list[int]
    zhongqi_events: list[SpanTermEvent]


def run_debug_spans(
    *,
    new_moon_calculator: NewMoonCalculator,
    term_calculator: SkyfieldPrincipalTermCalculator,
    year: int,
    pad_days: int,
    degrees: list[int],
    tz: str,
    ephemeris_path: str,
    only_anomalies: bool,
    include_newmoons: bool,
) -> dict:
    start_utc, end_utc = year_window_utc(year, pad_days)
    new_moons = new_moon_calculator.find_new_moons_between(
        NewMoonWindowRequest(
            tz=tz,
            ephemeris_path=ephemeris_path,
            start_utc=start_utc,
            end_utc=end_utc,
        )
    )
    spans = build_spans(new_moons)

    term_events: list[tuple[int, PrincipalTermEvent]] = []
    for degree in degrees:
        events = term_calculator.find_events_between(
            PrincipalTermWindowRequest(
                degree=degree,
                tz=tz,
                ephemeris_path=ephemeris_path,
                start_utc=start_utc,
                end_utc=end_utc,
            )
        )
        term_events.extend((degree, event) for event in events)

    span_payloads = assign_terms_to_spans(spans, term_events)
    zeros = [span["index"] for span in span_payloads if span["zhongqi_count"] == 0]
    many = [span["index"] for span in span_payloads if span["zhongqi_count"] >= 2]

    if only_anomalies:
        span_payloads = [s for s in span_payloads if s["zhongqi_count"] == 0 or s["zhongqi_count"] >= 2]

    payload = {
        "year": year,
        "tz": tz,
        "ephemeris_path": ephemeris_path,
        "search_window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
        },
        "spans": span_payloads,
        "summary": {
            "span_count": len(spans),
            "zeros": zeros,
            "many": many,
        },
        "status": "ok",
    }
    if include_newmoons:
        payload["new_moons"] = [asdict(nm) for nm in new_moons]
    return payload


def build_spans(new_moons: list) -> list[tuple[int, datetime, datetime, str, str]]:
    parsed = [datetime.fromisoformat(nm.utc) for nm in new_moons]
    spans: list[tuple[int, datetime, datetime, str, str]] = []
    for index in range(len(new_moons) - 1):
        start = parsed[index]
        end = parsed[index + 1]
        spans.append(
            (
                index,
                start,
                end,
                new_moons[index].local_date,
                new_moons[index + 1].local_date,
            )
        )
    return spans


def assign_terms_to_spans(
    spans: list[tuple[int, datetime, datetime, str, str]],
    term_events: list[tuple[int, PrincipalTermEvent]],
) -> list[dict]:
    parsed_terms: list[tuple[int, datetime, PrincipalTermEvent]] = []
    for degree, event in term_events:
        parsed_terms.append((degree, datetime.fromisoformat(event.utc), event))

    payloads: list[dict] = []
    for index, start, end, start_local_date, end_local_date_exclusive in spans:
        inside: list[SpanTermEvent] = []
        for degree, term_dt, event in parsed_terms:
            if start <= term_dt < end:
                inside.append(
                    SpanTermEvent(
                        deg=degree,
                        utc=event.utc,
                        local=event.local,
                        local_date=event.local_date,
                    )
                )
        inside.sort(key=lambda e: (e.utc, e.deg))
        degrees = sorted({event.deg for event in inside})
        payloads.append(
            asdict(
                MoonSpan(
                    index=index,
                    start_utc=start.isoformat(),
                    end_utc=end.isoformat(),
                    start_local_date=start_local_date,
                    end_local_date_exclusive=end_local_date_exclusive,
                    zhongqi_count=len(inside),
                    zhongqi_degrees=degrees,
                    zhongqi_events=inside,
                )
            )
        )
    return payloads
