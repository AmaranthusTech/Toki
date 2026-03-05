from __future__ import annotations

import json

import shintoki.cli as cli
from shintoki.cli import run


def test_debug_term_json_shape(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ephemeris = data_dir / "de440s.bsp"
    ephemeris.touch()

    def fake_run_debug_term(*_args, **kwargs):
        return {
            "year": kwargs["year"],
            "degree": kwargs["degree"],
            "tz": kwargs["tz"],
            "ephemeris_path": kwargs["ephemeris_path"],
            "events": [
                {
                    "utc": "2033-12-21T13:46:00+00:00",
                    "jst": "2033-12-21T22:46:00+09:00",
                    "local": "2033-12-21T22:46:00+09:00",
                    "local_date": "2033-12-21",
                }
            ],
            "status": "ok",
            "note": None,
        }

    monkeypatch.setattr(cli, "run_debug_term", fake_run_debug_term)
    exit_code = run(["debug-term", "--year", "2033", "--deg", "270", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["events"][0]["utc"]
    assert payload["events"][0]["local"]
    assert payload["events"][0]["local_date"]
    assert payload["ephemeris_path"] == str(ephemeris.resolve())


def test_debug_term_fails_without_ephemeris(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)

    exit_code = run(["debug-term", "--year", "2033", "--deg", "270", "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing_ephemeris_path" in captured.out
