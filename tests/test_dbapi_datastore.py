from __future__ import annotations

from datetime import date
import json
import sqlite3

from shintoki.dbapi.datastore import DataStore, build_range_response


def _make_db(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            """
            CREATE TABLE daily_calendar (
                d TEXT PRIMARY KEY,
                tz TEXT NOT NULL,
                lunar_year INTEGER NOT NULL,
                lunar_month INTEGER NOT NULL,
                lunar_day INTEGER NOT NULL,
                is_leap INTEGER NOT NULL,
                rokuyo TEXT NOT NULL,
                sekki_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        meta_rows = [
            ("schema_version", "1"),
            ("range_start", "2017-06-09"),
            ("range_end", "2017-06-10"),
            ("tz", "Asia/Tokyo"),
            ("window_mode", "solstice-to-solstice"),
            ("algo_version", "0.2.0"),
            ("ephemeris_name", "de440s.bsp"),
            ("ephemeris_sha256", "dummy"),
            ("generated_at", "2026-01-01T00:00:00+00:00"),
        ]
        conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", meta_rows)
        conn.execute(
            """
            INSERT INTO daily_calendar(
              d, tz, lunar_year, lunar_month, lunar_day, is_leap, rokuyo, sekki_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2017-06-09",
                "Asia/Tokyo",
                2017,
                5,
                15,
                0,
                "先勝",
                json.dumps([]),
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_datastore_day_meta_and_range(tmp_path) -> None:
    db = tmp_path / "calendar.sqlite3"
    _make_db(db)
    store = DataStore(db)

    assert store.exists() is True
    meta = store.get_meta()
    assert meta["schema_version"] == "1"
    assert meta["range_start"] == "2017-06-09"
    coverage = store.get_coverage()
    assert coverage["meta_range_start"] == "2017-06-09"
    assert coverage["data_min_date"] == "2017-06-09"
    assert coverage["row_count"] == 1
    assert store.get_meta_issues() == []

    got = store.get_day(date(2017, 6, 9), tz="Asia/Tokyo")
    assert got is not None
    assert got["lunar"]["month"] == 5

    missing = store.get_day(date(2017, 6, 10), tz="Asia/Tokyo")
    assert missing is None

    payload, status = build_range_response(
        store,
        start=date(2017, 6, 9),
        end=date(2017, 6, 10),
        tz="Asia/Tokyo",
        strict=False,
    )
    assert status == 200
    assert payload["missing"] == ["2017-06-10"]

    payload2, status2 = build_range_response(
        store,
        start=date(2017, 6, 9),
        end=date(2017, 6, 10),
        tz="Asia/Tokyo",
        strict=True,
    )
    assert status2 == 404
    assert payload2["error"]["code"] == "not_found"


def test_meta_issues_when_missing_keys(tmp_path) -> None:
    db = tmp_path / "calendar.sqlite3"
    _make_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("DELETE FROM meta WHERE key='generated_at'")
        conn.commit()
    finally:
        conn.close()
    store = DataStore(db)
    codes = {issue["code"] for issue in store.get_meta_issues()}
    assert "meta_missing_key" in codes
