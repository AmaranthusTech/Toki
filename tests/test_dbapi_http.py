from __future__ import annotations

from datetime import date
import importlib.util
import json
import sqlite3

import pytest

from shintoki.dbapi.http import resolve_sqlite_path


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
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            [
                ("schema_version", "1"),
                ("range_start", "2017-06-09"),
                ("range_end", "2017-06-10"),
                ("tz", "Asia/Tokyo"),
                ("window_mode", "solstice-to-solstice"),
                ("algo_version", "0.2.0"),
                ("ephemeris_name", "de440s.bsp"),
                ("ephemeris_sha256", "dummy"),
                ("generated_at", "2026-01-01T00:00:00+00:00"),
            ],
        )
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


_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None
_HAS_HTTPX = importlib.util.find_spec("httpx") is not None


@pytest.mark.skipif(not (_HAS_FASTAPI and _HAS_HTTPX), reason="fastapi/httpx not installed")
def test_dbapi_endpoints_not_found_and_strict(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from shintoki.dbapi.http import create_app

    db = tmp_path / "calendar.sqlite3"
    _make_db(db)
    client = TestClient(create_app(sqlite_path=str(db)))

    health = client.get("/health")
    assert health.status_code == 200
    hp = health.json()
    assert hp["sqlite_exists"] is True
    assert hp["sqlite_path"].endswith("calendar.sqlite3")
    assert hp["counts"]["day_cache"] == 1
    assert hp["coverage"]["meta_range_start"] == "2017-06-09"
    assert hp["meta"]["schema_version"] == "1"
    assert hp["meta_issues"] == []

    day_hit = client.get("/api/v1/day", params={"date": "2017-06-09", "tz": "Asia/Tokyo"})
    assert day_hit.status_code == 200
    assert day_hit.json()["day"]["lunar"]["day"] == 15

    day_miss = client.get("/api/v1/day", params={"date": "2017-06-10", "tz": "Asia/Tokyo"})
    assert day_miss.status_code == 404
    assert day_miss.json()["error"]["code"] == "not_found"

    rng_soft = client.get(
        "/api/v1/range",
        params={"start": "2017-06-09", "end": "2017-06-10", "tz": "Asia/Tokyo", "strict": 0},
    )
    assert rng_soft.status_code == 200
    assert rng_soft.json()["missing"] == ["2017-06-10"]

    rng_strict = client.get(
        "/api/v1/range",
        params={"start": "2017-06-09", "end": "2017-06-10", "tz": "Asia/Tokyo", "strict": 1},
    )
    assert rng_strict.status_code == 404
    assert rng_strict.json()["error"]["missing"] == ["2017-06-10"]


@pytest.mark.skipif(not (_HAS_FASTAPI and _HAS_HTTPX), reason="fastapi/httpx not installed")
def test_dbapi_admin_precompute_todo(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from shintoki.dbapi.http import create_app

    db = tmp_path / "calendar.sqlite3"
    _make_db(db)
    client = TestClient(create_app(sqlite_path=str(db)))
    res = client.post(
        "/admin/precompute",
        json={
            "start": date(2017, 6, 9).isoformat(),
            "end": date(2017, 6, 10).isoformat(),
            "tz": "Asia/Tokyo",
        },
    )
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "not_implemented"


def test_resolve_sqlite_path_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("SHINTOKI_DB_PATH", "/tmp/from-env.sqlite3")
    assert resolve_sqlite_path(None) == "/tmp/from-env.sqlite3"
    assert resolve_sqlite_path("/tmp/from-arg.sqlite3") == "/tmp/from-arg.sqlite3"
