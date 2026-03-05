from __future__ import annotations

import json

from shintoki.cli import run


def test_doctor_without_ephemeris_path_shows_error(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)

    exit_code = run(["--format", "json", "doctor"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing_ephemeris_path" in captured.out
    assert "set --ephemeris-path or SHINTOKI_EPHEMERIS_PATH" in captured.out


def test_doctor_auto_detects_default_ephemeris(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHINTOKI_EPHEMERIS_PATH", raising=False)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ephemeris = data_dir / "de440s.bsp"
    ephemeris.touch()

    exit_code = run(["--format", "json", "doctor"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["ephemeris_path"] == str(ephemeris.resolve())
    assert payload["issues"] == []
