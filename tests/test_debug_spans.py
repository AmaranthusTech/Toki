from __future__ import annotations

from shintoki.cli import run
from shintoki.core.new_moon import NewMoonEvent
from shintoki.core.solar_terms import PrincipalTermEvent
from shintoki.services.debug_spans import assign_terms_to_spans, build_spans, run_debug_spans


class FakeNewMoonCalculator:
    def find_new_moons_between(self, _req):
        return [
            NewMoonEvent(
                utc="2033-01-01T00:00:00+00:00",
                local="2033-01-01T09:00:00+09:00",
                local_date="2033-01-01",
            ),
            NewMoonEvent(
                utc="2033-01-10T00:00:00+00:00",
                local="2033-01-10T09:00:00+09:00",
                local_date="2033-01-10",
            ),
            NewMoonEvent(
                utc="2033-01-20T00:00:00+00:00",
                local="2033-01-20T09:00:00+09:00",
                local_date="2033-01-20",
            ),
            NewMoonEvent(
                utc="2033-01-30T00:00:00+00:00",
                local="2033-01-30T09:00:00+09:00",
                local_date="2033-01-30",
            ),
        ]


class FakeTermCalculator:
    def find_events_between(self, req):
        if req.degree == 0:
            return [
                PrincipalTermEvent(
                    utc="2033-01-05T00:00:00+00:00",
                    jst="2033-01-05T09:00:00+09:00",
                    local="2033-01-05T09:00:00+09:00",
                    local_date="2033-01-05",
                ),
                PrincipalTermEvent(
                    utc="2033-01-12T00:00:00+00:00",
                    jst="2033-01-12T09:00:00+09:00",
                    local="2033-01-12T09:00:00+09:00",
                    local_date="2033-01-12",
                ),
            ]
        if req.degree == 30:
            return [
                PrincipalTermEvent(
                    utc="2033-01-14T00:00:00+00:00",
                    jst="2033-01-14T09:00:00+09:00",
                    local="2033-01-14T09:00:00+09:00",
                    local_date="2033-01-14",
                ),
            ]
        return []


def test_debug_spans_fails_without_ephemeris(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)
    exit_code = run(["debug-spans", "--year", "2033", "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing_ephemeris_path" in captured.out


def test_assign_terms_left_closed_right_open() -> None:
    spans = build_spans(
        [
            NewMoonEvent(
                utc="2033-01-01T00:00:00+00:00",
                local="2033-01-01T09:00:00+09:00",
                local_date="2033-01-01",
            ),
            NewMoonEvent(
                utc="2033-01-10T00:00:00+00:00",
                local="2033-01-10T09:00:00+09:00",
                local_date="2033-01-10",
            ),
            NewMoonEvent(
                utc="2033-01-20T00:00:00+00:00",
                local="2033-01-20T09:00:00+09:00",
                local_date="2033-01-20",
            ),
        ]
    )
    events = [
        (
            270,
            PrincipalTermEvent(
                utc="2033-01-10T00:00:00+00:00",
                jst="2033-01-10T09:00:00+09:00",
                local="2033-01-10T09:00:00+09:00",
                local_date="2033-01-10",
            ),
        ),
    ]
    payload = assign_terms_to_spans(spans, events)

    assert payload[0]["zhongqi_count"] == 0
    assert payload[1]["zhongqi_count"] == 1


def test_run_debug_spans_summary_with_fakes() -> None:
    payload = run_debug_spans(
        new_moon_calculator=FakeNewMoonCalculator(),
        term_calculator=FakeTermCalculator(),
        year=2033,
        pad_days=60,
        degrees=[0, 30],
        tz="Asia/Tokyo",
        ephemeris_path="/tmp/fake.bsp",
        only_anomalies=False,
        include_newmoons=True,
    )

    assert payload["summary"]["span_count"] == 3
    assert payload["summary"]["zeros"] == [2]
    assert payload["summary"]["many"] == [1]
    assert "new_moons" in payload
    assert len(payload["spans"]) == 3
