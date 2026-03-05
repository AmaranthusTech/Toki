from __future__ import annotations

from datetime import date

from shintoki.public import LunarYMD, NamedMonth, TermEvent, gregorian_to_lunar, lunar_months_for_year


def test_public_symbols_importable() -> None:
    assert LunarYMD is not None
    assert TermEvent is not None
    assert NamedMonth is not None
    assert callable(gregorian_to_lunar)
    assert callable(lunar_months_for_year)


def test_lunar_months_for_year_uses_named_schema(monkeypatch) -> None:
    import shintoki.public.core as core

    monkeypatch.setattr(core, "_resolve_ephemeris_or_raise", lambda _: "dummy")
    monkeypatch.setattr(
        core,
        "_months_for_year",
        lambda year, tz, ephemeris_path, window_mode: (
            {
                "span_index": 10,
                "month_no": 11,
                "is_leap": False,
                "start_utc": "2033-01-01T00:00:00+00:00",
                "end_utc": "2033-01-30T00:00:00+00:00",
                "start_local_date": "2033-01-01",
                "end_local_date_exclusive": "2033-01-30",
                "has_zhongqi": True,
                "zhongqi_degrees": [270],
            },
        ),
    )
    rows = core.lunar_months_for_year(2033)
    assert len(rows) == 1
    assert rows[0].month_no == 11
    assert rows[0].zhongqi_degrees == [270]


def test_gregorian_to_lunar_computes_day(monkeypatch) -> None:
    import shintoki.public.core as core

    monkeypatch.setattr(
        core,
        "_find_named_month",
        lambda target_date, tz, ephemeris_path, window_mode: NamedMonth(
            span_index=1,
            month_no=5,
            is_leap=False,
            start_utc="2033-06-01T00:00:00+00:00",
            end_utc="2033-07-01T00:00:00+00:00",
            start_local_date="2033-06-01",
            end_local_date_exclusive="2033-07-01",
            has_zhongqi=True,
            zhongqi_degrees=[90],
        ),
    )
    monkeypatch.setattr(core, "_resolve_ephemeris_or_raise", lambda _: "dummy")
    got = core.gregorian_to_lunar(date(2033, 6, 10))
    assert isinstance(got, LunarYMD)
    assert got.month == 5
    assert got.day == 10
