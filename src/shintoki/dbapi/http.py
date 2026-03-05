from __future__ import annotations

from datetime import date
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shintoki.dbapi.datastore import DataStore, build_range_response

DEFAULT_DB_PATH = "./data/cache/shintoki.sqlite3"


class PrecomputeRequest(BaseModel):
    start: date
    end: date
    tz: str = "Asia/Tokyo"
    window_mode: str = "solstice-to-solstice"
    pad_days: int = 60


def resolve_sqlite_path(sqlite_path: str | None = None) -> str:
    return sqlite_path or os.getenv("SHINTOKI_DB_PATH") or DEFAULT_DB_PATH


def create_app(sqlite_path: str | None = None) -> FastAPI:
    app = FastAPI(title="ShinToki DB API", version="1.0.0")
    store = DataStore(resolve_sqlite_path(sqlite_path))

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "sqlite_path": str(store.sqlite_path),
            "sqlite_exists": store.exists(),
            "coverage": store.get_coverage(),
            "meta": store.get_meta(),
            "counts": store.get_counts(),
            "meta_issues": store.get_meta_issues(),
        }

    @app.get("/api/v1/day")
    def api_day(
        date_value: date = Query(alias="date"),
        tz: str = Query(default="Asia/Tokyo"),
    ):
        payload = store.get_day(date_value, tz=tz)
        if payload is None:
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error": {
                        "code": "not_found",
                        "missing": [date_value.isoformat()],
                        "hint": "precompute required",
                    },
                },
            )
        return {
            "ok": True,
            "date": date_value.isoformat(),
            "tz": tz,
            "day": {
                "date": payload["date"],
                "lunar": payload["lunar"],
                "rokuyo": payload["rokuyo"],
                "sekki": payload["sekki"],
            },
        }

    @app.get("/api/v1/range")
    def api_range(
        start: date,
        end: date,
        tz: str = Query(default="Asia/Tokyo"),
        strict: int = Query(default=0),
    ):
        if end < start:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": {"code": "invalid_range", "message": "end must be >= start"}},
            )
        payload, status = build_range_response(store, start=start, end=end, tz=tz, strict=bool(strict))
        if status != 200:
            return JSONResponse(status_code=status, content=payload)
        return payload

    @app.post("/admin/precompute")
    def admin_precompute(req: PrecomputeRequest):
        # TODO: hook up export-sqlite / background job orchestration.
        return JSONResponse(
            status_code=501,
            content={
                "ok": False,
                "error": {
                    "code": "not_implemented",
                    "message": "precompute trigger is TODO. use CLI export-sqlite for now.",
                },
                "request": req.model_dump(mode="json"),
            },
        )

    return app


default_sqlite = Path(resolve_sqlite_path())
app = create_app(sqlite_path=str(default_sqlite))
