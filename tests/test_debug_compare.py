from __future__ import annotations

import importlib.util
import json

import shintoki.cli as cli
from shintoki.cli import run
from shintoki.services import debug_compare


def test_debug_compare_cli_json_keys(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "de440s.bsp").touch()

    def fake_run_debug_compare(**kwargs):
        return {
            "year": kwargs["year"],
            "tz": kwargs["tz"],
            "ephemeris_path": kwargs["ephemeris_path"],
            "window_mode": kwargs["window_mode"],
            "pad_days": kwargs["pad_days"],
            "shintoki": {
                "spans_summary": {"zeros": [11], "many": []},
                "months_summary": {"leap_spans": [11], "issues": []},
                "months": [],
                "spans": [],
                "summary": {
                    "span_count_raw": 16,
                    "span_count_normalized": 13,
                    "zeros": [11],
                    "many": [],
                    "leap_spans": [11],
                    "issues": [],
                },
            },
            "jcal": {
                "ok": False,
                "error_type": "ImportError",
                "error_message": "missing",
                "traceback_hint": "ImportError at import_module",
            },
            "compare_summary": {
                "jcal_available": False,
                "jcal_reason": "jcal months info not available",
                "shintoki": {
                    "span_count_normalized": 13,
                    "zeros": [11],
                    "many": [],
                    "leap_spans": [11],
                },
                "jcal": {
                    "span_count_normalized": None,
                    "zeros": None,
                    "many": None,
                    "leap_spans": None,
                },
                "months_match": None,
                "mismatches": [],
            },
        }

    monkeypatch.setattr(cli, "run_debug_compare", fake_run_debug_compare)
    exit_code = run(
        [
            "debug-compare",
            "--year",
            "2033",
            "--window-mode",
            "solstice-to-solstice",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["window_mode"] == "solstice-to-solstice"
    assert "shintoki" in payload
    assert "jcal" in payload
    assert "compare_summary" in payload
    assert "summary" in payload["shintoki"]


def test_probe_jcal_without_module_or_runtime_error() -> None:
    payload = debug_compare.probe_jcal_2033(year=2033)
    if importlib.util.find_spec("jcal") is None:
        assert payload["ok"] is False
        assert payload["error_type"] in {"ModuleNotFoundError", "ImportError"}


def test_probe_jcal_when_installed_not_module_not_found() -> None:
    import pytest

    if importlib.util.find_spec("jcal") is None:
        pytest.skip("jcal not installed in this environment")

    payload = debug_compare.probe_jcal_2033(year=2033)
    assert payload["error_type"] != "ModuleNotFoundError"


def test_compare_summary_when_jcal_months_unavailable() -> None:
    shintoki_payload = {
        "summary": {
            "span_count_normalized": 13,
            "zeros": [11],
            "many": [],
            "leap_spans": [11],
        },
        "months": [{"span_index": 11, "month_no": 7, "is_leap": True}],
    }
    jcal_payload = {"ok": False, "error_type": "RuntimeError"}
    summary = debug_compare._build_compare_summary(shintoki_payload, jcal_payload)
    assert summary["jcal_available"] is False
    assert summary["shintoki"]["span_count_normalized"] == 13
    assert summary["months_match"] is None


def test_compare_summary_month_mismatch() -> None:
    shintoki_payload = {
        "summary": {
            "span_count_normalized": 13,
            "zeros": [11],
            "many": [],
            "leap_spans": [11],
        },
        "months": [
            {"span_index": 0, "month_no": 11, "is_leap": False},
            {"span_index": 1, "month_no": 12, "is_leap": False},
        ],
    }
    jcal_payload = {
        "summary": {
            "span_count_normalized": 13,
            "zeros": [11],
            "many": [],
            "leap_spans": [11],
        },
        "months": [
            {"span_index": 0, "month_no": 11, "is_leap": False},
            {"span_index": 1, "month_no": 1, "is_leap": False},
        ],
    }
    summary = debug_compare._build_compare_summary(shintoki_payload, jcal_payload)
    assert summary["jcal_available"] is True
    assert summary["months_match"] is False
    assert len(summary["mismatches"]) == 1
