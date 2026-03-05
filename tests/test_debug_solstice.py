from __future__ import annotations

import json
from pathlib import Path

from shintoki.cli import run


def test_debug_solstice_returns_events_for_2033(capsys, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)

    exit_code = run(["debug-solstice", "--year", "2033", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["year"] == 2033
    assert payload["degree"] == 270
    assert isinstance(payload["events"], list)
    assert payload["events"]

    event = payload["events"][0]
    assert "utc" in event
    assert "jst" in event
    assert "jst_date" in event
    assert "+" in event["utc"] or "Z" in event["utc"]
    assert "+" in event["jst"]
    assert len(event["jst_date"]) == 10


def test_debug_solstice_fails_without_ephemeris(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)

    exit_code = run(["debug-solstice", "--year", "2033", "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing_ephemeris_path" in captured.out
