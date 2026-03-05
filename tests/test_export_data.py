from __future__ import annotations

from datetime import date
import sqlite3

from shintoki.services.export_data import run_export_sqlite, run_validate_sqlite


def test_export_sqlite_writes_meta(monkeypatch, tmp_path) -> None:
    eph = tmp_path / "de440s.bsp"
    eph.write_bytes(b"dummy-ephemeris")
    out = tmp_path / "calendar.sqlite3"

    monkeypatch.setattr(
        "shintoki.services.export_data._build_day_row",
        lambda d, tz, ephemeris_path, window_mode: {
            "date": d.isoformat(),
            "tz": tz,
            "lunar_year": 2017,
            "lunar_month": 5,
            "lunar_day": 1,
            "is_leap": False,
            "rokuyo": "先勝",
            "sekki": [],
        },
    )
    payload = run_export_sqlite(
        start=date(2017, 6, 1),
        end=date(2017, 6, 2),
        tz="Asia/Tokyo",
        out=str(out),
        ephemeris_path=str(eph),
        window_mode="solstice-to-solstice",
    )
    assert payload["ok"] is True
    assert payload["meta"]["schema_version"] == "1"
    assert payload["meta"]["range_start"] == "2017-06-01"
    assert payload["meta"]["range_end"] == "2017-06-02"

    conn = sqlite3.connect(out)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    assert meta["schema_version"] == "1"
    assert meta["range_start"] == "2017-06-01"
    assert meta["range_end"] == "2017-06-02"
    assert meta["tz"] == "Asia/Tokyo"
    assert meta["window_mode"] == "solstice-to-solstice"
    assert meta["ephemeris_name"] == "de440s.bsp"


def test_validate_sqlite_detects_meta_mismatch(monkeypatch, tmp_path) -> None:
    eph = tmp_path / "de440s.bsp"
    eph.write_bytes(b"dummy-ephemeris")
    out = tmp_path / "calendar.sqlite3"

    monkeypatch.setattr(
        "shintoki.services.export_data._build_day_row",
        lambda d, tz, ephemeris_path, window_mode: {
            "date": d.isoformat(),
            "tz": tz,
            "lunar_year": 2017,
            "lunar_month": 5,
            "lunar_day": 1,
            "is_leap": False,
            "rokuyo": "先勝",
            "sekki": [],
        },
    )
    run_export_sqlite(
        start=date(2017, 6, 1),
        end=date(2017, 6, 1),
        tz="Asia/Tokyo",
        out=str(out),
        ephemeris_path=str(eph),
        window_mode="solstice-to-solstice",
    )

    conn = sqlite3.connect(out)
    try:
        conn.execute("UPDATE meta SET value='raw' WHERE key='window_mode'")
        conn.execute("UPDATE meta SET value='2017-06-99' WHERE key='range_start'")
        conn.commit()
    finally:
        conn.close()

    result = run_validate_sqlite(
        sqlite_path=str(out),
        tz="Asia/Tokyo",
        ephemeris_path=str(eph),
        samples=1,
        seed=1,
        window_mode="solstice-to-solstice",
    )
    assert result["ok"] is False
    codes = {issue["code"] for issue in result["meta_issues"]}
    assert "meta_window_mode_mismatch" in codes
    assert "meta_range_start_mismatch" in codes
