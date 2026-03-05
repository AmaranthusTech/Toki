from __future__ import annotations

import json
from datetime import datetime

import shintoki.cli as cli
from shintoki.cli import run
from shintoki.core.new_moon import NewMoonEvent
from shintoki.core.solar_terms import PrincipalTermEvent
from shintoki.services.debug_months import normalize_spans, run_debug_months


class FakeNewMoonCalculator:
    def find_new_moons_between(self, _req):
        return [
            NewMoonEvent(
                utc="2033-09-01T00:00:00+00:00",
                local="2033-09-01T09:00:00+09:00",
                local_date="2033-09-01",
            ),
            NewMoonEvent(
                utc="2033-10-01T00:00:00+00:00",
                local="2033-10-01T09:00:00+09:00",
                local_date="2033-10-01",
            ),
            NewMoonEvent(
                utc="2033-11-01T00:00:00+00:00",
                local="2033-11-01T09:00:00+09:00",
                local_date="2033-11-01",
            ),
            NewMoonEvent(
                utc="2033-12-01T00:00:00+00:00",
                local="2033-12-01T09:00:00+09:00",
                local_date="2033-12-01",
            ),
        ]


class FakeTermCalculator:
    def find_events_between(self, req):
        if req.degree == 240:
            return [
                PrincipalTermEvent(
                    utc="2033-09-10T00:00:00+00:00",
                    jst="2033-09-10T09:00:00+09:00",
                    local="2033-09-10T09:00:00+09:00",
                    local_date="2033-09-10",
                )
            ]
        if req.degree == 270:
            return [
                PrincipalTermEvent(
                    utc="2033-10-10T00:00:00+00:00",
                    jst="2033-10-10T09:00:00+09:00",
                    local="2033-10-10T09:00:00+09:00",
                    local_date="2033-10-10",
                )
            ]
        if req.degree == 300:
            return [
                PrincipalTermEvent(
                    utc="2033-12-10T00:00:00+00:00",
                    jst="2033-12-10T09:00:00+09:00",
                    local="2033-12-10T09:00:00+09:00",
                    local_date="2033-12-10",
                )
            ]
        return []


def test_debug_months_fails_without_ephemeris(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)

    exit_code = run(["debug-months", "--year", "2033", "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing_ephemeris_path" in captured.out


def test_run_debug_months_marks_leap_span() -> None:
    payload = run_debug_months(
        new_moon_calculator=FakeNewMoonCalculator(),
        term_calculator=FakeTermCalculator(),
        year=2033,
        pad_days=60,
        degrees=[240, 270, 300],
        tz="Asia/Tokyo",
        ephemeris_path="/tmp/fake.bsp",
        strict_expect_leap=False,
        window_mode="raw",
    )

    assert payload["summary"]["anchor_span_index"] == 1
    assert payload["summary"]["anchor_term_utc"] == "2033-10-10T00:00:00+00:00"
    assert payload["summary"]["anchor_span_start_utc"] == "2033-10-01T00:00:00+00:00"
    assert payload["summary"]["anchor_span_end_utc"] == "2033-11-01T00:00:00+00:00"
    assert payload["summary"]["issues"] == []
    assert payload["summary"]["span_count_raw"] == payload["summary"]["span_count_normalized"]
    assert payload["summary"]["window_mode"] == "raw"
    assert payload["summary"]["zero_spans"] == [2]
    assert payload["summary"]["leap_spans"] == [2]


def test_debug_months_cli_with_monkeypatched_service(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "de440s.bsp").touch()

    def fake_run_debug_months(**kwargs):
        assert kwargs["strict_expect_leap"] is True
        assert kwargs["window_mode"] == "calendar-year"
        return {
            "year": 2033,
            "tz": "Asia/Tokyo",
            "ephemeris_path": str((data_dir / "de440s.bsp").resolve()),
            "months": [],
            "summary": {
                "anchor_span_index": 1,
                "anchor_term_utc": "2033-12-22T00:00:00+00:00",
                "anchor_span_start_utc": "2033-12-01T00:00:00+00:00",
                "anchor_span_end_utc": "2034-01-01T00:00:00+00:00",
                "span_count_raw": 16,
                "span_count_normalized": 13,
                "window_mode": "calendar-year",
                "normalization_note": "dummy",
                "normalization_issues": [],
                "months_count": 0,
                "leap_spans": [11],
                "zero_spans": [11],
                "issues": [{"code": "strict_expect_leap_conflict", "message": "dummy"}],
            },
            "status": "ok",
        }

    monkeypatch.setattr(cli, "run_debug_months", fake_run_debug_months)
    exit_code = run(["debug-months", "--year", "2033", "--strict-expect-leap", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["summary"]["leap_spans"] == [11]
    assert payload["summary"]["issues"][0]["code"] == "strict_expect_leap_conflict"


def test_normalize_spans_raw_mode_keeps_count() -> None:
    spans = _build_span_payloads_for_modes()
    normalized, _, _ = normalize_spans(
        spans,
        {},
        year=2033,
        window_mode="raw",
        tz="Asia/Tokyo",
    )
    assert len(normalized) == len(spans)


def test_normalize_spans_calendar_year_reduces_count() -> None:
    spans = _build_span_payloads_for_modes()
    normalized, _, _ = normalize_spans(
        spans,
        {},
        year=2033,
        window_mode="calendar-year",
        tz="Asia/Tokyo",
    )
    assert len(normalized) < len(spans)


def test_normalize_spans_solstice_to_solstice_yields_12_or_13() -> None:
    spans = _build_span_payloads_for_modes()
    normalized, _, issues = normalize_spans(
        spans,
        {},
        year=2033,
        window_mode="solstice-to-solstice",
        tz="Asia/Tokyo",
    )
    assert len(normalized) in (12, 13) or any(i["code"] == "normalized_span_count_unexpected" for i in issues)


def test_strict_applies_to_normalized_12_spans(monkeypatch) -> None:
    normalized_12 = _build_normalized_12_with_zero()

    def fake_normalize(*_args, **_kwargs):
        return normalized_12, "forced", []

    monkeypatch.setattr("shintoki.services.debug_months.normalize_spans", fake_normalize)
    non_strict = run_debug_months(
        new_moon_calculator=FakeNewMoonCalculator(),
        term_calculator=FakeTermCalculator(),
        year=2033,
        pad_days=60,
        degrees=[240, 270, 300],
        tz="Asia/Tokyo",
        ephemeris_path="/tmp/fake.bsp",
        strict_expect_leap=False,
        window_mode="calendar-year",
    )
    strict = run_debug_months(
        new_moon_calculator=FakeNewMoonCalculator(),
        term_calculator=FakeTermCalculator(),
        year=2033,
        pad_days=60,
        degrees=[240, 270, 300],
        tz="Asia/Tokyo",
        ephemeris_path="/tmp/fake.bsp",
        strict_expect_leap=True,
        window_mode="calendar-year",
    )

    assert non_strict["summary"]["leap_spans"] == [8]
    assert strict["summary"]["leap_spans"] == []
    assert any(i["code"] == "strict_expect_leap_conflict" for i in strict["summary"]["issues"])


def _build_span_payloads_for_modes() -> list[dict]:
    rows = []
    base = datetime.fromisoformat("2032-11-01T00:00:00+00:00")
    for i in range(16):
        start = base.replace(month=((11 + i - 1) % 12) + 1, year=2032 + ((11 + i - 1) // 12))
        end_month_total = 11 + i
        end = base.replace(month=((end_month_total) % 12) + 1, year=2032 + (end_month_total // 12))
        degrees = [((240 + 30 * i) % 360)]
        events = [{"deg": degrees[0], "utc": start.isoformat(), "local": start.isoformat(), "local_date": "x"}]
        if i == 1:
            degrees = [270]
            events = [{"deg": 270, "utc": "2032-12-21T00:00:00+00:00", "local": "x", "local_date": "x"}]
        if i == 14:
            degrees = [270]
            events = [{"deg": 270, "utc": "2033-12-22T00:00:00+00:00", "local": "x", "local_date": "x"}]
        rows.append(
            {
                "index": i,
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat(),
                "start_local_date": "x",
                "end_local_date_exclusive": "x",
                "zhongqi_count": len(degrees),
                "zhongqi_degrees": degrees,
                "zhongqi_events": events,
            }
        )
    return rows


def _build_normalized_12_with_zero() -> list[dict]:
    spans = []
    for i in range(12):
        deg = ((210 + 30 * i) % 360)
        if i == 0:
            deg = 270
        degrees = [deg]
        count = 1
        events = [{"deg": deg, "utc": f"2033-{(i%12)+1:02d}-10T00:00:00+00:00", "local": "x", "local_date": "x"}]
        if i == 8:
            degrees = []
            count = 0
            events = []
        spans.append(
            {
                "index": i,
                "start_utc": f"2033-{(i%12)+1:02d}-01T00:00:00+00:00",
                "end_utc": f"2033-{((i+1)%12)+1:02d}-01T00:00:00+00:00",
                "start_local_date": "x",
                "end_local_date_exclusive": "x",
                "zhongqi_count": count,
                "zhongqi_degrees": degrees,
                "zhongqi_events": events,
            }
        )
    return spans
