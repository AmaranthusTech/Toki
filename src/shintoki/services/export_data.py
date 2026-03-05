from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3

from shintoki import __version__ as SHINTOKI_VERSION
from shintoki.public import gregorian_to_lunar, principal_terms_between

ROKUYO = ("先勝", "友引", "先負", "仏滅", "大安", "赤口")
SCHEMA_VERSION = "1"


def run_export_sqlite(
    *,
    start: date,
    end: date,
    tz: str,
    out: str,
    ephemeris_path: str | None,
    window_mode: str = "solstice-to-solstice",
) -> dict:
    if end < start:
        raise ValueError("end must be >= start")

    out_path = Path(out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(out_path)
    try:
        _init_db(conn)
        meta = _build_meta(
            start=start,
            end=end,
            tz=tz,
            window_mode=window_mode,
            ephemeris_path=ephemeris_path,
        )
        _upsert_meta(conn, meta)
        exported = 0
        current = start
        while current <= end:
            row = _build_day_row(
                current,
                tz=tz,
                ephemeris_path=ephemeris_path,
                window_mode=window_mode,
            )
            _upsert_day(conn, row)
            exported += 1
            current += timedelta(days=1)
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "tz": tz,
        "window_mode": window_mode,
        "out": str(out_path),
        "meta": meta,
        "rows_exported": exported,
    }


def run_export_jsonl(
    *,
    start: date,
    end: date,
    tz: str,
    out: str,
    ephemeris_path: str | None,
    window_mode: str = "solstice-to-solstice",
) -> dict:
    if end < start:
        raise ValueError("end must be >= start")

    out_path = Path(out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    with out_path.open("w", encoding="utf-8") as fp:
        current = start
        while current <= end:
            row = _build_day_row(
                current,
                tz=tz,
                ephemeris_path=ephemeris_path,
                window_mode=window_mode,
            )
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
            exported += 1
            current += timedelta(days=1)

    return {
        "ok": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "tz": tz,
        "out": str(out_path),
        "rows_exported": exported,
    }


def run_validate_sqlite(
    *,
    sqlite_path: str,
    tz: str,
    ephemeris_path: str | None,
    samples: int = 10,
    seed: int = 2033,
    window_mode: str = "solstice-to-solstice",
) -> dict:
    db_path = Path(sqlite_path).resolve()
    if not db_path.exists():
        raise ValueError(f"sqlite not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        meta = _read_meta(conn)
        rows = list(
            conn.execute(
                """
                SELECT d, lunar_year, lunar_month, lunar_day, is_leap, rokuyo, sekki_json
                FROM daily_calendar
                ORDER BY d
                """
            )
        )
    finally:
        conn.close()

    if not rows:
        return {
            "ok": False,
            "sqlite_path": str(db_path),
            "meta": meta,
            "meta_issues": _validate_meta(
                meta,
                tz=tz,
                window_mode=window_mode,
                ephemeris_path=ephemeris_path,
                range_start=None,
                range_end=None,
            ),
            "sample_count": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "note": "no rows in sqlite",
        }

    rng = random.Random(seed)
    picked = rows if len(rows) <= samples else rng.sample(rows, samples)
    mismatches: list[dict] = []
    for row in picked:
        d = date.fromisoformat(row[0])
        expected = _build_day_row(
            d,
            tz=tz,
            ephemeris_path=ephemeris_path,
            window_mode=window_mode,
        )
        got = {
            "date": row[0],
            "lunar_year": row[1],
            "lunar_month": row[2],
            "lunar_day": row[3],
            "is_leap": bool(row[4]),
            "rokuyo": row[5],
            "sekki": json.loads(row[6]),
        }
        if not _same_day_payload(got, expected):
            mismatches.append({"date": row[0], "sqlite": got, "computed": expected})

    meta_issues = _validate_meta(
        meta,
        tz=tz,
        window_mode=window_mode,
        ephemeris_path=ephemeris_path,
        range_start=rows[0][0],
        range_end=rows[-1][0],
    )
    return {
        "ok": len(mismatches) == 0 and len(meta_issues) == 0,
        "sqlite_path": str(db_path),
        "meta": meta,
        "meta_issues": meta_issues,
        "sample_count": len(picked),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_calendar (
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_calendar_tz_d ON daily_calendar(tz, d)")


def _upsert_day(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO daily_calendar (
            d, tz, lunar_year, lunar_month, lunar_day, is_leap, rokuyo, sekki_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(d) DO UPDATE SET
            tz=excluded.tz,
            lunar_year=excluded.lunar_year,
            lunar_month=excluded.lunar_month,
            lunar_day=excluded.lunar_day,
            is_leap=excluded.is_leap,
            rokuyo=excluded.rokuyo,
            sekki_json=excluded.sekki_json,
            created_at=excluded.created_at
        """,
        (
            row["date"],
            row["tz"],
            row["lunar_year"],
            row["lunar_month"],
            row["lunar_day"],
            int(row["is_leap"]),
            row["rokuyo"],
            json.dumps(row["sekki"], ensure_ascii=False),
            datetime.now(tz=timezone.utc).isoformat(),
        ),
    )


def _upsert_meta(conn: sqlite3.Connection, meta: dict[str, str]) -> None:
    for key, value in meta.items():
        conn.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )


def _read_meta(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    return {key: value for key, value in rows}


def _build_meta(
    *,
    start: date,
    end: date,
    tz: str,
    window_mode: str,
    ephemeris_path: str | None,
) -> dict[str, str]:
    ephemeris = Path(ephemeris_path).resolve() if ephemeris_path else None
    ephemeris_name = ephemeris.name if ephemeris else ""
    ephemeris_sha256 = _sha256_file(ephemeris) if ephemeris and ephemeris.exists() else ""
    return {
        "schema_version": SCHEMA_VERSION,
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "tz": tz,
        "window_mode": window_mode,
        "algo_version": SHINTOKI_VERSION,
        "ephemeris_name": ephemeris_name,
        "ephemeris_sha256": ephemeris_sha256,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _validate_meta(
    meta: dict[str, str],
    *,
    tz: str,
    window_mode: str,
    ephemeris_path: str | None,
    range_start: str | None,
    range_end: str | None,
) -> list[dict[str, str]]:
    required = (
        "schema_version",
        "range_start",
        "range_end",
        "tz",
        "window_mode",
        "algo_version",
        "ephemeris_name",
        "ephemeris_sha256",
        "generated_at",
    )
    issues: list[dict[str, str]] = []
    for key in required:
        if key not in meta:
            issues.append({"code": "meta_missing_key", "message": f"missing meta key: {key}"})
    if meta.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            {
                "code": "meta_schema_version_mismatch",
                "message": f"schema_version={meta.get('schema_version')} expected={SCHEMA_VERSION}",
            }
        )
    if meta.get("tz") != tz:
        issues.append({"code": "meta_tz_mismatch", "message": f"meta tz={meta.get('tz')} expected={tz}"})
    if meta.get("window_mode") != window_mode:
        issues.append(
            {
                "code": "meta_window_mode_mismatch",
                "message": f"meta window_mode={meta.get('window_mode')} expected={window_mode}",
            }
        )
    if range_start is not None and meta.get("range_start") != range_start:
        issues.append(
            {
                "code": "meta_range_start_mismatch",
                "message": f"meta range_start={meta.get('range_start')} expected={range_start}",
            }
        )
    if range_end is not None and meta.get("range_end") != range_end:
        issues.append(
            {
                "code": "meta_range_end_mismatch",
                "message": f"meta range_end={meta.get('range_end')} expected={range_end}",
            }
        )
    if ephemeris_path:
        eph = Path(ephemeris_path).resolve()
        expected_name = eph.name
        expected_sha = _sha256_file(eph) if eph.exists() else ""
        if meta.get("ephemeris_name") != expected_name:
            issues.append(
                {
                    "code": "meta_ephemeris_name_mismatch",
                    "message": f"meta ephemeris_name={meta.get('ephemeris_name')} expected={expected_name}",
                }
            )
        if expected_sha and meta.get("ephemeris_sha256") != expected_sha:
            issues.append(
                {
                    "code": "meta_ephemeris_sha256_mismatch",
                    "message": "meta ephemeris_sha256 does not match expected file digest",
                }
            )
    return issues


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_day_row(
    d: date,
    *,
    tz: str,
    ephemeris_path: str | None,
    window_mode: str,
) -> dict:
    lunar = gregorian_to_lunar(d, tz=tz, ephemeris_path=ephemeris_path, window_mode=window_mode)
    terms = principal_terms_between(
        d,
        d + timedelta(days=1),
        tz=tz,
        ephemeris_path=ephemeris_path,
    )
    return {
        "date": d.isoformat(),
        "tz": tz,
        "lunar_year": lunar.year,
        "lunar_month": lunar.month,
        "lunar_day": lunar.day,
        "is_leap": lunar.is_leap,
        "rokuyo": ROKUYO[(lunar.month + lunar.day - 2) % 6],
        "sekki": [asdict(t) for t in terms],
    }


def _same_day_payload(lhs: dict, rhs: dict) -> bool:
    return (
        lhs["date"] == rhs["date"]
        and lhs["lunar_year"] == rhs["lunar_year"]
        and lhs["lunar_month"] == rhs["lunar_month"]
        and lhs["lunar_day"] == rhs["lunar_day"]
        and bool(lhs["is_leap"]) == bool(rhs["is_leap"])
        and lhs["rokuyo"] == rhs["rokuyo"]
        and lhs["sekki"] == rhs["sekki"]
    )
