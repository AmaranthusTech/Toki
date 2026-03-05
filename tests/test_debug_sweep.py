from __future__ import annotations

import json

import shintoki.cli as cli
from shintoki.cli import run


def test_debug_sweep_cli_json_shape(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "de440s.bsp").touch()

    def fake_run_debug_sweep(**kwargs):
        return {
            "start_year": kwargs["start_year"],
            "end_year": kwargs["end_year"],
            "window_mode": kwargs["window_mode"],
            "strict_expect_leap": kwargs["strict_expect_leap"],
            "years": [
                {
                    "year": kwargs["start_year"],
                    "shintoki": {
                        "span_count_normalized": 13,
                        "zeros": [11],
                        "many": [],
                        "leap_spans": [11],
                        "issues_count": 0,
                    },
                    "jcal": {"ok": False, "error_type": "RuntimeError"},
                    "compare_summary": {"months_match": None},
                }
            ],
            "summary": {
                "total": 1,
                "ok_count": 1,
                "jcal_ok_count": 0,
                "months_match_count": 0,
            },
        }

    monkeypatch.setattr(cli, "run_debug_sweep", fake_run_debug_sweep)
    code = run(
        [
            "debug-sweep",
            "--start-year",
            "2031",
            "--end-year",
            "2031",
            "--window-mode",
            "solstice-to-solstice",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["summary"]["total"] == 1
    assert payload["years"][0]["year"] == 2031


def test_debug_sweep_invalid_year_range(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "de440s.bsp").touch()

    code = run(
        [
            "debug-sweep",
            "--start-year",
            "2035",
            "--end-year",
            "2031",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["issues"][0]["code"] == "invalid_year_range"
