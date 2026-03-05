from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query

from shintoki.api.public import day_calendar, range_calendar


def create_app() -> FastAPI:
    app = FastAPI(title="ShinToki API", version="1.0.0")

    @app.get("/api/v1/day")
    def api_day(
        date_value: date = Query(alias="date"),
        tz: str = Query(default="Asia/Tokyo"),
        ephemeris_path: str | None = Query(default=None),
    ) -> dict:
        try:
            return day_calendar(date_value, tz=tz, ephemeris_path=ephemeris_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/range")
    def api_range(
        start: date,
        end: date,
        tz: str = Query(default="Asia/Tokyo"),
        ephemeris_path: str | None = Query(default=None),
    ) -> dict:
        try:
            return range_calendar(start, end, tz=tz, ephemeris_path=ephemeris_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
