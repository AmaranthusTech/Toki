from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class DataStore:
    sqlite_path: Path

    def __init__(self, sqlite_path: str | Path):
        object.__setattr__(self, "sqlite_path", Path(sqlite_path).resolve())

    def exists(self) -> bool:
        return self.sqlite_path.exists()

    def get_meta(self) -> dict[str, str]:
        if not self.exists():
            return {}
        with sqlite3.connect(self.sqlite_path) as conn:
            rows = conn.execute("SELECT key, value FROM meta").fetchall()
        return {str(k): str(v) for k, v in rows}

    def get_counts(self) -> dict[str, int]:
        if not self.exists():
            return {"day_cache": 0, "failures": 0}
        with sqlite3.connect(self.sqlite_path) as conn:
            day_cache = int(conn.execute("SELECT COUNT(*) FROM daily_calendar").fetchone()[0])
            failures = 0
            if self._table_exists(conn, "day_cache_failures"):
                failures = int(conn.execute("SELECT COUNT(*) FROM day_cache_failures").fetchone()[0])
        return {"day_cache": day_cache, "failures": failures}

    def get_coverage(self) -> dict[str, int | str | None]:
        meta = self.get_meta()
        if not self.exists():
            return {
                "meta_range_start": meta.get("range_start"),
                "meta_range_end": meta.get("range_end"),
                "data_min_date": None,
                "data_max_date": None,
                "row_count": 0,
            }

        with sqlite3.connect(self.sqlite_path) as conn:
            row = conn.execute("SELECT MIN(d), MAX(d), COUNT(*) FROM daily_calendar").fetchone()
        return {
            "meta_range_start": meta.get("range_start"),
            "meta_range_end": meta.get("range_end"),
            "data_min_date": row[0],
            "data_max_date": row[1],
            "row_count": int(row[2]),
        }

    def get_meta_issues(self) -> list[dict[str, str]]:
        meta = self.get_meta()
        coverage = self.get_coverage()
        required = (
            "schema_version",
            "range_start",
            "range_end",
            "tz",
            "window_mode",
            "algo_version",
            "ephemeris_sha256",
            "generated_at",
        )
        issues: list[dict[str, str]] = []
        for key in required:
            if key not in meta:
                issues.append({"code": "meta_missing_key", "message": f"missing meta key: {key}"})
        if (
            coverage["row_count"]
            and meta.get("range_start")
            and coverage["data_min_date"]
            and meta.get("range_start") > str(coverage["data_min_date"])
        ):
            issues.append(
                {
                    "code": "meta_range_start_outside_data",
                    "message": (
                        f"meta range_start={meta.get('range_start')} "
                        f"data_min_date={coverage['data_min_date']}"
                    ),
                }
            )
        if (
            coverage["row_count"]
            and meta.get("range_end")
            and coverage["data_max_date"]
            and meta.get("range_end") < str(coverage["data_max_date"])
        ):
            issues.append(
                {
                    "code": "meta_range_end_outside_data",
                    "message": f"meta range_end={meta.get('range_end')} data_max_date={coverage['data_max_date']}",
                }
            )
        return issues

    def get_day(self, target_date: date, tz: str = "Asia/Tokyo") -> dict | None:
        if not self.exists():
            return None
        with sqlite3.connect(self.sqlite_path) as conn:
            row = conn.execute(
                """
                SELECT d, tz, lunar_year, lunar_month, lunar_day, is_leap, rokuyo, sekki_json
                FROM daily_calendar
                WHERE d = ? AND tz = ?
                """,
                (target_date.isoformat(), tz),
            ).fetchone()
        if row is None:
            return None
        return _row_to_payload(row)

    def get_range(self, start: date, end: date, tz: str = "Asia/Tokyo") -> dict[str, dict]:
        if end < start:
            raise ValueError("end must be >= start")
        if not self.exists():
            return {}
        with sqlite3.connect(self.sqlite_path) as conn:
            rows = conn.execute(
                """
                SELECT d, tz, lunar_year, lunar_month, lunar_day, is_leap, rokuyo, sekki_json
                FROM daily_calendar
                WHERE d >= ? AND d <= ? AND tz = ?
                ORDER BY d
                """,
                (start.isoformat(), end.isoformat(), tz),
            ).fetchall()
        return {r[0]: _row_to_payload(r) for r in rows}

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None


def _row_to_payload(row: tuple) -> dict:
    return {
        "date": row[0],
        "tz": row[1],
        "lunar": {
            "year": int(row[2]),
            "month": int(row[3]),
            "day": int(row[4]),
            "is_leap": bool(row[5]),
        },
        "rokuyo": row[6],
        "sekki": json.loads(row[7]),
    }


def build_range_response(store: DataStore, start: date, end: date, tz: str, strict: bool) -> tuple[dict, int]:
    payload_by_date = store.get_range(start, end, tz=tz)
    rows: list[dict] = []
    missing: list[str] = []
    cur = start
    while cur <= end:
        key = cur.isoformat()
        if key in payload_by_date:
            day = payload_by_date[key]
            rows.append(
                {
                    "date": day["date"],
                    "lunar": day["lunar"],
                    "rokuyo": day["rokuyo"],
                    "sekki": day["sekki"],
                }
            )
        else:
            missing.append(key)
            rows.append({"date": key, "lunar": None, "rokuyo": None, "sekki": []})
        cur += timedelta(days=1)

    if strict and missing:
        return (
            {
                "ok": False,
                "error": {
                    "code": "not_found",
                    "missing": missing,
                    "hint": "precompute required",
                },
                "start": start.isoformat(),
                "end": end.isoformat(),
                "tz": tz,
            },
            404,
        )

    return (
        {
            "ok": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "tz": tz,
            "strict": strict,
            "missing": missing,
            "days": rows,
        },
        200,
    )
