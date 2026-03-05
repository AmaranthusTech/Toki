from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture()
def lunisolar_module():
    return pytest.importorskip("jcal.core.lunisolar")


def test_resolve_leap_span_pos_absorbs_zero_pos9(lunisolar_module) -> None:
    func = getattr(lunisolar_module, "_resolve_leap_span_pos_for_month_naming")

    class _DummySpan:
        def __init__(self, idx: int):
            self.idx = idx
            self.begin_utc = datetime(2033, 1, 1, tzinfo=timezone.utc).replace(month=(idx % 12) + 1)
            self.end_utc = self.begin_utc.replace(day=28)

    spans2 = [_DummySpan(i) for i in range(12)]
    zhongqi_events = [(0.0, datetime(2033, 1, 1, tzinfo=timezone.utc))]

    original_terms = getattr(lunisolar_module, "_terms_in_span_left_closed")
    original_bounds = getattr(lunisolar_module, "_span_bounds_utc")

    def fake_bounds(sp):
        return sp.begin_utc, sp.end_utc

    def fake_terms(s_utc, _e_utc, _events, *, epsilon_seconds=0):
        del epsilon_seconds
        if s_utc.month == 10:
            return []
        return [(0, datetime(2033, 1, 1, tzinfo=timezone.utc))]

    try:
        setattr(lunisolar_module, "_span_bounds_utc", fake_bounds)
        setattr(lunisolar_module, "_terms_in_span_left_closed", fake_terms)
        result = func(
            spans2,
            zhongqi_events,
            expect_leap=False,
            epsilon_seconds=0,
            spans2_offset=25,
        )
    finally:
        setattr(lunisolar_module, "_span_bounds_utc", original_bounds)
        setattr(lunisolar_module, "_terms_in_span_left_closed", original_terms)

    assert result == 9


def test_resolve_leap_span_many_recheck_with_utc_left_closed(lunisolar_module) -> None:
    func = getattr(lunisolar_module, "_resolve_leap_span_pos_for_month_naming")

    class _DummySpan:
        def __init__(self):
            self.begin_utc = datetime(2033, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            self.end_utc = datetime(2033, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

    spans2 = [_DummySpan()]
    zhongqi_events = [
        (0.0, datetime(2033, 1, 1, 0, 30, 0, tzinfo=timezone.utc)),  # before span start, same JST day
        (30.0, datetime(2033, 1, 1, 18, 0, 0, tzinfo=timezone.utc)),  # inside span
    ]

    result = func(
        spans2,
        zhongqi_events,
        expect_leap=False,
        epsilon_seconds=0,
        spans2_offset=0,
    )

    assert result is None


def test_resolve_leap_span_zero_recheck_only_when_expect_leap(lunisolar_module) -> None:
    func = getattr(lunisolar_module, "_resolve_leap_span_pos_for_month_naming")

    class _DummySpan:
        def __init__(self, start: datetime, end: datetime):
            self.begin_utc = start
            self.end_utc = end

    spans2 = [
        _DummySpan(datetime(2034, 1, 1, 0, 0, tzinfo=timezone.utc), datetime(2034, 1, 2, 0, 0, tzinfo=timezone.utc)),
        _DummySpan(datetime(2034, 1, 2, 0, 0, tzinfo=timezone.utc), datetime(2034, 1, 3, 0, 0, tzinfo=timezone.utc)),
    ]

    # For span0: day-basis misses term, UTC catches it.
    # For span1: truly zero in both day-basis and UTC.
    zhongqi_events = [(300.0, datetime(2034, 1, 1, 12, 0, tzinfo=timezone.utc))]

    original_terms = getattr(lunisolar_module, "_terms_in_span_left_closed")
    original_terms_utc = getattr(lunisolar_module, "_terms_in_span_utc_left_closed")
    original_bounds = getattr(lunisolar_module, "_span_bounds_utc")

    def fake_bounds(sp):
        return sp.begin_utc, sp.end_utc

    def fake_terms(s_utc, _e_utc, _events, *, epsilon_seconds=0):
        del epsilon_seconds
        if s_utc.day == 1:
            # emulate that the synthetic rescue term can be seen by day-basis
            # classification after re-check augmentation
            if len(_events) >= 2:
                return [(300, datetime(2034, 1, 1, 12, 0, tzinfo=timezone.utc))]
            return []
        return []

    def fake_terms_utc(s_utc, _e_utc, _events, *, epsilon_seconds=0):
        del epsilon_seconds
        if s_utc.day == 1:
            return [(300, datetime(2034, 1, 1, 12, 0, tzinfo=timezone.utc))]
        return []

    try:
        setattr(lunisolar_module, "_span_bounds_utc", fake_bounds)
        setattr(lunisolar_module, "_terms_in_span_left_closed", fake_terms)
        setattr(lunisolar_module, "_terms_in_span_utc_left_closed", fake_terms_utc)
        result = func(
            spans2,
            zhongqi_events,
            expect_leap=True,
            epsilon_seconds=0,
            spans2_offset=0,
        )
    finally:
        setattr(lunisolar_module, "_span_bounds_utc", original_bounds)
        setattr(lunisolar_module, "_terms_in_span_left_closed", original_terms)
        setattr(lunisolar_module, "_terms_in_span_utc_left_closed", original_terms_utc)

    assert result == 1


def test_gregorian_to_lunar_2033_returns_without_exception(lunisolar_module, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    eph = repo_root / "data" / "de440s.bsp"
    if not eph.exists():
        pytest.skip("ephemeris file is missing")

    monkeypatch.setenv("JCAL_EPHEMERIS_PATH", str(eph))
    monkeypatch.setenv("JCAL_EPHEMERIS", str(eph))
    monkeypatch.setenv("TOKI_EPHEMERIS_PATH", str(eph))
    monkeypatch.setenv("TOKI_EPHEMERIS", str(eph))
    monkeypatch.setenv("EPHEMERIS_PATH", str(eph))

    result = lunisolar_module.gregorian_to_lunar(date(2033, 6, 10))
    assert result is not None
