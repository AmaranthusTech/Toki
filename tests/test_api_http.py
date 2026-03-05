from __future__ import annotations

from datetime import date
import importlib.util

import pytest


_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None
_HAS_HTTPX = importlib.util.find_spec("httpx") is not None


@pytest.mark.skipif(not (_HAS_FASTAPI and _HAS_HTTPX), reason="fastapi/httpx not installed")
def test_api_day_endpoint(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from shintoki.api import http

    monkeypatch.setattr(
        http,
        "day_calendar",
        lambda target_date, tz, ephemeris_path=None: {
            "date": target_date.isoformat(),
            "tz": tz,
            "lunar": {"year": 2017, "month": 5, "day": 15, "is_leap": False},
            "rokuyo": "先勝",
            "sekki": [],
            "issues": [],
        },
    )
    client = TestClient(http.create_app())
    resp = client.get("/api/v1/day", params={"date": "2017-06-09", "tz": "Asia/Tokyo"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["date"] == "2017-06-09"
    assert payload["lunar"]["month"] == 5


@pytest.mark.skipif(not (_HAS_FASTAPI and _HAS_HTTPX), reason="fastapi/httpx not installed")
def test_api_range_endpoint(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from shintoki.api import http

    monkeypatch.setattr(
        http,
        "range_calendar",
        lambda start, end, tz, ephemeris_path=None: {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "tz": tz,
            "days": [{"date": date(2017, 6, 9).isoformat()}],
        },
    )
    client = TestClient(http.create_app())
    resp = client.get(
        "/api/v1/range",
        params={"start": "2017-06-09", "end": "2017-06-10", "tz": "Asia/Tokyo"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["start"] == "2017-06-09"
    assert len(payload["days"]) == 1
