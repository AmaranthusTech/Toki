from __future__ import annotations

import json

import shintoki.cli as cli
from shintoki.cli import run


def test_export_sqlite_cli_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "de440s.bsp").touch()

    monkeypatch.setattr(
        cli,
        "run_export_sqlite",
        lambda **kwargs: {
            "ok": True,
            "start": kwargs["start"].isoformat(),
            "end": kwargs["end"].isoformat(),
            "out": kwargs["out"],
            "rows_exported": 2,
        },
    )
    code = run(
        [
            "export-sqlite",
            "--start",
            "2017-06-01",
            "--end",
            "2017-06-02",
            "--out",
            "tmp/calendar.sqlite3",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["rows_exported"] == 2


def test_export_jsonl_invalid_date(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    code = run(
        [
            "export-jsonl",
            "--start",
            "2017/06/01",
            "--end",
            "2017-06-02",
            "--out",
            "tmp/calendar.jsonl",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["issues"][0]["code"] == "invalid_date"


def test_validate_sqlite_cli_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "de440s.bsp").touch()

    monkeypatch.setattr(
        cli,
        "run_validate_sqlite",
        lambda **kwargs: {
            "ok": True,
            "sqlite_path": kwargs["sqlite_path"],
            "sample_count": kwargs["samples"],
            "mismatch_count": 0,
            "mismatches": [],
        },
    )
    code = run(
        [
            "validate-sqlite",
            "--sqlite",
            "tmp/calendar.sqlite3",
            "--samples",
            "3",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["sample_count"] == 3


def test_export_sqlite_preset_cli_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "de440s.bsp").touch()

    monkeypatch.setattr(
        cli,
        "run_export_sqlite",
        lambda **kwargs: {
            "ok": True,
            "start": kwargs["start"].isoformat(),
            "end": kwargs["end"].isoformat(),
            "out": kwargs["out"],
            "rows_exported": 10,
        },
    )
    code = run(
        [
            "export-sqlite",
            "--preset",
            "lite-2000-2050",
            "--out",
            "tmp/calendar.sqlite3",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["start"] == "2000-01-01"
    assert payload["end"] == "2050-12-31"
