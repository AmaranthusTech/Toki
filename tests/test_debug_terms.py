from __future__ import annotations

import json

import shintoki.cli as cli
from shintoki.cli import run


def test_debug_terms_json_has_degree_keys(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "de440s.bsp").touch()

    def fake_run_debug_terms(*_args, **kwargs):
        assert kwargs["year"] == 2033
        return {
            "year": 2033,
            "tz": kwargs["tz"],
            "ephemeris_path": kwargs["ephemeris_path"],
            "events_by_degree": {
                "0": [{"utc": "2033-01-01T00:00:00+00:00", "local": "x", "local_date": "2033-01-01"}],
                "30": [{"utc": "2033-01-30T00:00:00+00:00", "local": "x", "local_date": "2033-01-30"}],
                "60": [{"utc": "2033-02-28T00:00:00+00:00", "local": "x", "local_date": "2033-02-28"}],
                "270": [{"utc": "2033-12-21T13:46:00+00:00", "local": "x", "local_date": "2033-12-21"}],
            },
            "status": "ok",
        }

    monkeypatch.setattr(cli, "run_debug_terms", fake_run_debug_terms)
    exit_code = run(["debug-terms", "--year", "2033", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert "270" in payload["events_by_degree"]
    assert "0" in payload["events_by_degree"]
    assert "30" in payload["events_by_degree"]
    assert len(payload["events_by_degree"]) >= 4
