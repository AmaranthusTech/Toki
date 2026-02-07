from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from jcal.api.public import get_calendar_day, get_calendar_range


def _find_ephemeris_path() -> Path | None:
    env = os.environ.get("TOKI_EPHEMERIS_PATH")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p

    repo = Path(__file__).resolve().parents[1]
    for name in ("de440s.bsp", "de421.bsp"):
        p = repo / "data" / name
        if p.exists():
            return p
    return None


def _require_ephemeris() -> Path:
    p = _find_ephemeris_path()
    if p is None:
        pytest.skip("ephemeris not found (set TOKI_EPHEMERIS_PATH or place data/de440s.bsp)")
    return p


def _assert_iso_jst(s: str) -> datetime:
    assert s.endswith("+09:00")
    dt = datetime.fromisoformat(s)
    assert dt.tzinfo is not None
    return dt


def test_calendar_day_sunrise_sunset_tokyo():
    ephem_path = _require_ephemeris()
    res = get_calendar_day(
        "2017-06-24",
        tz="Asia/Tokyo",
        ephemeris_path=ephem_path,
        day_basis="jst",
    )
    astro = res["astronomy"]
    assert astro["sunrise"] is not None
    assert astro["sunset"] is not None

    sunrise = _assert_iso_jst(astro["sunrise"])
    sunset = _assert_iso_jst(astro["sunset"])
    assert sunrise < sunset


def test_calendar_range_sunrise_sunset_tokyo():
    ephem_path = _require_ephemeris()
    res = get_calendar_range(
        "2017-06-24",
        "2017-06-26",
        tz="Asia/Tokyo",
        ephemeris_path=ephem_path,
        day_basis="jst",
    )

    for day in res["days"]:
        astro = day["astronomy"]
        assert astro["sunrise"] is not None
        assert astro["sunset"] is not None

        sunrise = _assert_iso_jst(astro["sunrise"])
        sunset = _assert_iso_jst(astro["sunset"])
        assert sunrise < sunset
