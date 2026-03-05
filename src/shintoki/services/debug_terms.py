from __future__ import annotations

from dataclasses import asdict

from shintoki.core.solar_terms import (
    PrincipalTermCalculator,
    PrincipalTermRequest,
)


def run_debug_term(
    calculator: PrincipalTermCalculator,
    *,
    year: int,
    degree: int,
    tz: str,
    ephemeris_path: str,
) -> dict:
    req = PrincipalTermRequest(
        year=year,
        degree=degree,
        tz=tz,
        ephemeris_path=ephemeris_path,
    )
    result = calculator.find_events(req)
    return asdict(result)


def run_debug_terms(
    calculator: PrincipalTermCalculator,
    *,
    year: int,
    degrees: list[int],
    tz: str,
    ephemeris_path: str,
) -> dict:
    events_by_degree: dict[str, list[dict[str, str]]] = {}
    for degree in degrees:
        payload = run_debug_term(
            calculator,
            year=year,
            degree=degree,
            tz=tz,
            ephemeris_path=ephemeris_path,
        )
        events_by_degree[str(degree)] = payload["events"]

    return {
        "year": year,
        "tz": tz,
        "ephemeris_path": ephemeris_path,
        "events_by_degree": events_by_degree,
        "status": "ok",
    }
