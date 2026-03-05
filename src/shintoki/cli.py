from __future__ import annotations

import argparse
import importlib.util
import json
import logging
from dataclasses import asdict
from datetime import date
from typing import Any

from shintoki.core.new_moon import SkyfieldNewMoonCalculator
from shintoki.core.solar_terms import SkyfieldPrincipalTermCalculator
from shintoki.core.solstice import SkyfieldSolarTermCalculator
from shintoki.logging import configure_logging
from shintoki.services.bench import run_bench_smoke
from shintoki.services.debug_compare import run_debug_compare
from shintoki.services.debug_months import run_debug_months
from shintoki.services.debug_sweep import run_debug_sweep
from shintoki.services.debug_solstice import run_debug_solstice
from shintoki.services.debug_spans import run_debug_spans
from shintoki.services.debug_terms import run_debug_term, run_debug_terms
from shintoki.services.doctor import resolve_ephemeris_path, run_doctor
from shintoki.services.export_data import run_export_jsonl, run_export_sqlite, run_validate_sqlite

LOG = logging.getLogger("shintoki.cli")
ALLOWED_DEGREES = tuple(range(0, 360, 30))
EXPORT_PRESETS = {
    "full-1900-2100": (date(1900, 1, 1), date(2100, 12, 31)),
    "lite-2000-2050": (date(2000, 1, 1), date(2050, 12, 31)),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shintoki", description="ShinToki CLI")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_debug = subparsers.add_parser("debug-solstice", help="Debug solstice event lookup")
    p_debug.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_debug.add_argument("--year", type=int, required=True)
    p_debug.add_argument("--deg", type=float, default=270)
    p_debug.add_argument("--tz", default="Asia/Tokyo")
    p_debug.add_argument("--ephemeris-path", default=None)

    p_doctor = subparsers.add_parser("doctor", help="Check local runtime environment")
    p_doctor.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_doctor.add_argument("--ephemeris-path", default=None)

    p_bench = subparsers.add_parser("bench-smoke", help="Run benchmark smoke test")
    p_bench.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_bench.add_argument("--iterations", type=int, default=10_000)

    p_term = subparsers.add_parser("debug-term", help="Debug principal term for one degree")
    p_term.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_term.add_argument("--year", type=int, required=True)
    p_term.add_argument("--deg", type=int, required=True)
    p_term.add_argument("--tz", default="Asia/Tokyo")
    p_term.add_argument("--ephemeris-path", default=None)

    p_terms = subparsers.add_parser("debug-terms", help="Debug principal terms for many degrees")
    p_terms.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_terms.add_argument("--year", type=int, required=True)
    p_terms.add_argument("--degrees", default=None)
    p_terms.add_argument("--tz", default="Asia/Tokyo")
    p_terms.add_argument("--ephemeris-path", default=None)

    p_spans = subparsers.add_parser(
        "debug-spans",
        help="Inspect new-moon spans and principal-term assignment",
    )
    p_spans.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_spans.add_argument("--year", type=int, required=True)
    p_spans.add_argument("--pad-days", type=int, default=60)
    p_spans.add_argument("--degrees", default=None)
    p_spans.add_argument("--tz", default="Asia/Tokyo")
    p_spans.add_argument("--ephemeris-path", default=None)
    p_spans.add_argument("--only-anomalies", action="store_true")
    p_spans.add_argument("--include-newmoons", action="store_true")

    p_months = subparsers.add_parser("debug-months", help="Inspect lunar month naming with leap")
    p_months.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_months.add_argument("--year", type=int, required=True)
    p_months.add_argument("--pad-days", type=int, default=60)
    p_months.add_argument("--degrees", default=None)
    p_months.add_argument("--tz", default="Asia/Tokyo")
    p_months.add_argument("--ephemeris-path", default=None)
    p_months.add_argument(
        "--window-mode",
        choices=("calendar-year", "solstice-to-solstice", "raw"),
        default="calendar-year",
    )
    p_months.add_argument("--only-anomalies", action="store_true")
    p_months.add_argument("--strict-expect-leap", action="store_true")

    p_compare = subparsers.add_parser("debug-compare", help="Compare ShinToki spans/months with jcal probe")
    p_compare.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_compare.add_argument("--year", type=int, required=True)
    p_compare.add_argument("--pad-days", type=int, default=60)
    p_compare.add_argument("--degrees", default=None)
    p_compare.add_argument("--tz", default="Asia/Tokyo")
    p_compare.add_argument("--ephemeris-path", default=None)
    p_compare.add_argument(
        "--window-mode",
        choices=("calendar-year", "solstice-to-solstice", "raw"),
        default="calendar-year",
    )
    p_compare.add_argument("--strict-expect-leap", action="store_true")

    p_sweep = subparsers.add_parser("debug-sweep", help="Sweep boundary years for compare diagnostics")
    p_sweep.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_sweep.add_argument("--start-year", type=int, required=True)
    p_sweep.add_argument("--end-year", type=int, required=True)
    p_sweep.add_argument("--pad-days", type=int, default=60)
    p_sweep.add_argument("--degrees", default=None)
    p_sweep.add_argument("--tz", default="Asia/Tokyo")
    p_sweep.add_argument("--ephemeris-path", default=None)
    p_sweep.add_argument(
        "--window-mode",
        choices=("calendar-year", "solstice-to-solstice", "raw"),
        default="calendar-year",
    )
    p_sweep.add_argument("--strict-expect-leap", action="store_true")

    p_api = subparsers.add_parser("api", help="Run stable HTTP API")
    api_subparsers = p_api.add_subparsers(dest="api_command", required=True)
    p_api_serve = api_subparsers.add_parser("serve", help="Serve FastAPI app")
    p_api_serve.add_argument("--host", default="127.0.0.1")
    p_api_serve.add_argument("--port", type=int, default=8010)
    p_api_serve.add_argument("--reload", action="store_true")
    p_api_serve.add_argument("--log-level", default="info")

    p_api_db = subparsers.add_parser("api-db", help="Run DB-backed API for bloom")
    api_db_subparsers = p_api_db.add_subparsers(dest="api_db_command", required=True)
    p_api_db_serve = api_db_subparsers.add_parser("serve", help="Serve DB-backed FastAPI app")
    p_api_db_serve.add_argument("--host", default="127.0.0.1")
    p_api_db_serve.add_argument("--port", type=int, default=8011)
    p_api_db_serve.add_argument("--reload", action="store_true")
    p_api_db_serve.add_argument("--log-level", default="info")
    p_api_db_serve.add_argument("--sqlite-path", default=None)

    p_export_sqlite = subparsers.add_parser("export-sqlite", help="Export daily calendar data to sqlite")
    p_export_sqlite.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_export_sqlite.add_argument("--start")
    p_export_sqlite.add_argument("--end")
    p_export_sqlite.add_argument("--preset", choices=tuple(EXPORT_PRESETS.keys()))
    p_export_sqlite.add_argument("--tz", default="Asia/Tokyo")
    p_export_sqlite.add_argument("--out", required=True)
    p_export_sqlite.add_argument("--ephemeris-path", default=None)
    p_export_sqlite.add_argument(
        "--window-mode",
        choices=("calendar-year", "solstice-to-solstice", "raw"),
        default="solstice-to-solstice",
    )

    p_export_jsonl = subparsers.add_parser("export-jsonl", help="Export daily calendar data to jsonl")
    p_export_jsonl.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_export_jsonl.add_argument("--start", required=True)
    p_export_jsonl.add_argument("--end", required=True)
    p_export_jsonl.add_argument("--tz", default="Asia/Tokyo")
    p_export_jsonl.add_argument("--out", required=True)
    p_export_jsonl.add_argument("--ephemeris-path", default=None)
    p_export_jsonl.add_argument(
        "--window-mode",
        choices=("calendar-year", "solstice-to-solstice", "raw"),
        default="solstice-to-solstice",
    )

    p_validate_sqlite = subparsers.add_parser(
        "validate-sqlite",
        help="Validate sqlite export against library calculation",
    )
    p_validate_sqlite.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    p_validate_sqlite.add_argument("--sqlite", required=True)
    p_validate_sqlite.add_argument("--tz", default="Asia/Tokyo")
    p_validate_sqlite.add_argument("--samples", type=int, default=10)
    p_validate_sqlite.add_argument("--seed", type=int, default=2033)
    p_validate_sqlite.add_argument("--ephemeris-path", default=None)
    p_validate_sqlite.add_argument(
        "--window-mode",
        choices=("calendar-year", "solstice-to-solstice", "raw"),
        default="solstice-to-solstice",
    )

    return parser


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        return asdict(obj)
    raise TypeError(f"Type is not JSON serializable: {type(obj)!r}")


def _emit(data: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))
        return

    for key, value in data.items():
        print(f"{key}: {value}")


def _emit_terms_text(payload: dict[str, Any]) -> None:
    for degree in sorted(payload["events_by_degree"].keys(), key=lambda x: int(x)):
        events = payload["events_by_degree"][degree]
        if not events:
            print(f"deg={degree} events=0")
            continue
        for event in events:
            print(
                f"deg={degree} utc={event['utc']} local={event['local']} local_date={event['local_date']}"
            )


def _emit_spans_text(payload: dict[str, Any]) -> None:
    for span in payload["spans"]:
        prefix = ""
        if span["zhongqi_count"] == 0:
            prefix = "[ZERO] "
        elif span["zhongqi_count"] >= 2:
            prefix = "[MANY] "
        print(
            f"{prefix}span#{span['index']} {span['start_utc']} {span['end_utc']} "
            f"zhongqi_count={span['zhongqi_count']} degrees={span['zhongqi_degrees']}"
        )


def _emit_months_text(payload: dict[str, Any]) -> None:
    for month in payload["months"]:
        prefix = "[LEAP] " if month["is_leap"] else ""
        print(
            f"{prefix}span#{month['span_index']} month={month['month_no']} leap={month['is_leap']} "
            f"zhongqi={month['zhongqi_degrees']} start={month['start_utc']} end={month['end_utc']}"
        )


def _emit_sweep_text(payload: dict[str, Any]) -> None:
    for item in payload["years"]:
        year = item["year"]
        sh = item["shintoki"]
        jc = item["jcal"]
        comp = item["compare_summary"]
        print(
            f"{year} | sh_ok={sh['issues_count'] == 0} | zeros={sh['zeros']} | many={sh['many']} "
            f"| leap={sh['leap_spans']} | jcal_ok={jc['ok']} | jcal_err={jc['error_type']} "
            f"| months_match={comp['months_match']}"
        )


def _parse_degrees(raw: str | None) -> list[int]:
    if raw is None:
        return list(ALLOWED_DEGREES)

    degrees: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            degree = int(token)
        except ValueError:
            raise ValueError(f"invalid degree: {token}") from None
        if degree not in ALLOWED_DEGREES:
            raise ValueError(f"degree must be in 0..330 by 30: {degree}")
        degrees.append(degree)
    if not degrees:
        raise ValueError("degrees list is empty")
    return degrees


def _missing_ephemeris_payload() -> dict[str, Any]:
    return {
        "ok": False,
        "issues": [
            {
                "code": "missing_ephemeris_path",
                "message": "ephemeris path is required. set --ephemeris-path or SHINTOKI_EPHEMERIS_PATH.",
            }
        ],
    }


def _parse_iso_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid date format (YYYY-MM-DD): {raw}") from exc


def _resolve_export_range(start_raw: str | None, end_raw: str | None, preset: str | None) -> tuple[date, date]:
    if preset:
        if start_raw or end_raw:
            raise ValueError("do not combine --preset with --start/--end")
        return EXPORT_PRESETS[preset]
    if not start_raw or not end_raw:
        raise ValueError("require --start and --end, or use --preset")
    return _parse_iso_date(start_raw), _parse_iso_date(end_raw)


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)

    if args.command == "debug-solstice":
        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        LOG.info(
            "debug-solstice called year=%s deg=%s tz=%s ephemeris=%s",
            args.year,
            args.deg,
            args.tz,
            resolved,
        )
        result = run_debug_solstice(
            SkyfieldSolarTermCalculator(),
            year=args.year,
            degree=args.deg,
            tz=args.tz,
            ephemeris_path=str(resolved),
        )
        _emit(asdict(result), args.format)
        return 0

    if args.command == "doctor":
        report = run_doctor(args.ephemeris_path)
        payload = {
            "ok": report.ok,
            "python_version": report.python_version,
            "ephemeris_path": report.ephemeris_path,
            "ephemeris_exists": report.ephemeris_exists,
            "issues": [asdict(issue) for issue in report.issues],
        }
        _emit(payload, args.format)
        return 0 if report.ok else 2

    if args.command == "bench-smoke":
        LOG.info("bench-smoke called iterations=%s", args.iterations)
        report = run_bench_smoke(iterations=args.iterations)
        _emit(asdict(report), args.format)
        return 0

    if args.command == "debug-term":
        if args.deg not in ALLOWED_DEGREES:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_degree", "message": "degree must be in 0..330 by 30"}],
            }
            _emit(payload, args.format)
            return 2

        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        payload = run_debug_term(
            SkyfieldPrincipalTermCalculator(),
            year=args.year,
            degree=args.deg,
            tz=args.tz,
            ephemeris_path=str(resolved),
        )
        LOG.info(
            "debug-term year=%s degrees=%s tz=%s ephemeris_path=%s found_count=%s",
            args.year,
            [args.deg],
            args.tz,
            resolved,
            len(payload["events"]),
        )
        _emit(payload, args.format)
        return 0

    if args.command == "debug-terms":
        try:
            degrees = _parse_degrees(args.degrees)
        except ValueError as exc:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_degrees", "message": str(exc)}],
            }
            _emit(payload, args.format)
            return 2

        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        payload = run_debug_terms(
            SkyfieldPrincipalTermCalculator(),
            year=args.year,
            degrees=degrees,
            tz=args.tz,
            ephemeris_path=str(resolved),
        )
        found_count = sum(len(v) for v in payload["events_by_degree"].values())
        LOG.info(
            "debug-terms year=%s degrees=%s tz=%s ephemeris_path=%s found_count=%s",
            args.year,
            degrees,
            args.tz,
            resolved,
            found_count,
        )
        if args.format == "json":
            _emit(payload, args.format)
        else:
            _emit_terms_text(payload)
        return 0

    if args.command == "debug-spans":
        try:
            degrees = _parse_degrees(args.degrees)
        except ValueError as exc:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_degrees", "message": str(exc)}],
            }
            _emit(payload, args.format)
            return 2

        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        payload = run_debug_spans(
            new_moon_calculator=SkyfieldNewMoonCalculator(),
            term_calculator=SkyfieldPrincipalTermCalculator(),
            year=args.year,
            pad_days=args.pad_days,
            degrees=degrees,
            tz=args.tz,
            ephemeris_path=str(resolved),
            only_anomalies=args.only_anomalies,
            include_newmoons=args.include_newmoons,
        )
        found_count = sum(span["zhongqi_count"] for span in payload["spans"])
        LOG.info(
            "debug-spans year=%s degrees=%s tz=%s ephemeris_path=%s found_count=%s",
            args.year,
            degrees,
            args.tz,
            resolved,
            found_count,
        )
        if args.format == "json":
            _emit(payload, args.format)
        else:
            _emit_spans_text(payload)
        return 0

    if args.command == "debug-months":
        try:
            degrees = _parse_degrees(args.degrees)
        except ValueError as exc:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_degrees", "message": str(exc)}],
            }
            _emit(payload, args.format)
            return 2

        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        payload = run_debug_months(
            new_moon_calculator=SkyfieldNewMoonCalculator(),
            term_calculator=SkyfieldPrincipalTermCalculator(),
            year=args.year,
            pad_days=args.pad_days,
            degrees=degrees,
            tz=args.tz,
            ephemeris_path=str(resolved),
            only_anomalies=args.only_anomalies,
            strict_expect_leap=args.strict_expect_leap,
            window_mode=args.window_mode,
        )
        found_count = len(payload["months"])
        LOG.info(
            "debug-months year=%s degrees=%s tz=%s ephemeris_path=%s found_count=%s",
            args.year,
            degrees,
            args.tz,
            resolved,
            found_count,
        )
        if args.format == "json":
            _emit(payload, args.format)
        else:
            _emit_months_text(payload)
        return 0

    if args.command == "debug-compare":
        try:
            degrees = _parse_degrees(args.degrees)
        except ValueError as exc:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_degrees", "message": str(exc)}],
            }
            _emit(payload, args.format)
            return 2

        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        payload = run_debug_compare(
            new_moon_calculator=SkyfieldNewMoonCalculator(),
            term_calculator=SkyfieldPrincipalTermCalculator(),
            year=args.year,
            tz=args.tz,
            ephemeris_path=str(resolved),
            pad_days=args.pad_days,
            window_mode=args.window_mode,
            degrees=degrees,
            strict_expect_leap=args.strict_expect_leap,
        )
        LOG.info(
            "debug-compare year=%s window_mode=%s tz=%s ephemeris_path=%s",
            args.year,
            args.window_mode,
            args.tz,
            resolved,
        )
        _emit(payload, args.format)
        return 0

    if args.command == "debug-sweep":
        if args.start_year > args.end_year:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_year_range", "message": "start-year must be <= end-year"}],
            }
            _emit(payload, args.format)
            return 2

        try:
            degrees = _parse_degrees(args.degrees)
        except ValueError as exc:
            payload = {
                "ok": False,
                "issues": [{"code": "invalid_degrees", "message": str(exc)}],
            }
            _emit(payload, args.format)
            return 2

        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2

        payload = run_debug_sweep(
            new_moon_calculator=SkyfieldNewMoonCalculator(),
            term_calculator=SkyfieldPrincipalTermCalculator(),
            start_year=args.start_year,
            end_year=args.end_year,
            tz=args.tz,
            ephemeris_path=str(resolved),
            pad_days=args.pad_days,
            window_mode=args.window_mode,
            degrees=degrees,
            strict_expect_leap=args.strict_expect_leap,
        )
        LOG.info(
            "debug-sweep start_year=%s end_year=%s window_mode=%s tz=%s ephemeris_path=%s",
            args.start_year,
            args.end_year,
            args.window_mode,
            args.tz,
            resolved,
        )
        if args.format == "json":
            _emit(payload, args.format)
        else:
            _emit_sweep_text(payload)
        return 0

    if args.command == "api":
        if args.api_command == "serve":
            missing = [name for name in ("fastapi", "uvicorn") if importlib.util.find_spec(name) is None]
            if missing:
                payload = {
                    "ok": False,
                    "issues": [
                        {
                            "code": "missing_api_dependencies",
                            "message": (
                                "missing API dependencies: "
                                + ", ".join(missing)
                                + ". install with: pip install -e '.[dev,api]'"
                            ),
                        }
                    ],
                }
                _emit(payload, args.format)
                return 2
            import uvicorn

            uvicorn.run(
                "shintoki.api.http:app",
                host=args.host,
                port=args.port,
                reload=args.reload,
                log_level=args.log_level,
            )
            return 0
        parser.error(f"Unsupported api command: {args.api_command}")
        return 2

    if args.command == "api-db":
        if args.api_db_command == "serve":
            missing = [name for name in ("fastapi", "uvicorn") if importlib.util.find_spec(name) is None]
            if missing:
                payload = {
                    "ok": False,
                    "issues": [
                        {
                            "code": "missing_api_dependencies",
                            "message": (
                                "missing API dependencies: "
                                + ", ".join(missing)
                                + ". install with: pip install -e '.[dev,api]'"
                            ),
                        }
                    ],
                }
                _emit(payload, args.format)
                return 2
            from shintoki.dbapi.http import create_app
            import uvicorn

            uvicorn.run(
                create_app(sqlite_path=args.sqlite_path),
                host=args.host,
                port=args.port,
                reload=args.reload,
                log_level=args.log_level,
            )
            return 0
        parser.error(f"Unsupported api-db command: {args.api_db_command}")
        return 2

    if args.command in {"export-sqlite", "export-jsonl"}:
        try:
            if args.command == "export-sqlite":
                start, end = _resolve_export_range(args.start, args.end, args.preset)
            else:
                start = _parse_iso_date(args.start)
                end = _parse_iso_date(args.end)
        except ValueError as exc:
            payload = {"ok": False, "issues": [{"code": "invalid_date", "message": str(exc)}]}
            _emit(payload, args.format)
            return 2
        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2
        try:
            if args.command == "export-sqlite":
                payload = run_export_sqlite(
                    start=start,
                    end=end,
                    tz=args.tz,
                    out=args.out,
                    ephemeris_path=str(resolved),
                    window_mode=args.window_mode,
                )
            else:
                payload = run_export_jsonl(
                    start=start,
                    end=end,
                    tz=args.tz,
                    out=args.out,
                    ephemeris_path=str(resolved),
                    window_mode=args.window_mode,
                )
        except ValueError as exc:
            payload = {"ok": False, "issues": [{"code": "invalid_args", "message": str(exc)}]}
            _emit(payload, args.format)
            return 2
        _emit(payload, args.format)
        return 0

    if args.command == "validate-sqlite":
        resolved = resolve_ephemeris_path(args.ephemeris_path)
        if resolved is None:
            _emit(_missing_ephemeris_payload(), args.format)
            return 2
        try:
            payload = run_validate_sqlite(
                sqlite_path=args.sqlite,
                tz=args.tz,
                ephemeris_path=str(resolved),
                samples=args.samples,
                seed=args.seed,
                window_mode=args.window_mode,
            )
        except ValueError as exc:
            payload = {"ok": False, "issues": [{"code": "invalid_args", "message": str(exc)}]}
            _emit(payload, args.format)
            return 2
        _emit(payload, args.format)
        return 0 if payload.get("ok") else 2

    parser.error(f"Unsupported command: {args.command}")
    return 2
