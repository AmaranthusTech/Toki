from __future__ import annotations

from shintoki.core.solstice import SolsticeRequest, SolsticeResult, SolarTermCalculator


def run_debug_solstice(
    calculator: SolarTermCalculator,
    *,
    year: int,
    degree: float,
    tz: str,
    ephemeris_path: str,
) -> SolsticeResult:
    req = SolsticeRequest(year=year, degree=degree, tz=tz, ephemeris_path=ephemeris_path)
    return calculator.find_event(req)
