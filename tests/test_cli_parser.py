from __future__ import annotations

from shintoki.cli import build_parser


def test_debug_solstice_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "debug-solstice",
            "--year",
            "2033",
            "--format",
            "json",
            "--tz",
            "Asia/Tokyo",
        ]
    )

    assert args.command == "debug-solstice"
    assert args.format == "json"
    assert args.year == 2033
    assert args.deg == 270
    assert args.tz == "Asia/Tokyo"
    assert args.ephemeris_path is None


def test_debug_sweep_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "debug-sweep",
            "--start-year",
            "2031",
            "--end-year",
            "2035",
            "--window-mode",
            "solstice-to-solstice",
            "--format",
            "json",
        ]
    )

    assert args.command == "debug-sweep"
    assert args.start_year == 2031
    assert args.end_year == 2035
    assert args.window_mode == "solstice-to-solstice"
    assert args.format == "json"


def test_api_serve_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "api",
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "8011",
            "--reload",
        ]
    )

    assert args.command == "api"
    assert args.api_command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 8011
    assert args.reload is True


def test_api_db_serve_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "api-db",
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "8022",
            "--sqlite-path",
            "tmp/calendar.sqlite3",
        ]
    )
    assert args.command == "api-db"
    assert args.api_db_command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 8022
    assert args.sqlite_path == "tmp/calendar.sqlite3"


def test_export_sqlite_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "export-sqlite",
            "--start",
            "2017-06-01",
            "--end",
            "2017-06-02",
            "--out",
            "tmp/calendar.sqlite3",
        ]
    )
    assert args.command == "export-sqlite"
    assert args.start == "2017-06-01"
    assert args.end == "2017-06-02"
    assert args.out == "tmp/calendar.sqlite3"


def test_export_sqlite_preset_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "export-sqlite",
            "--preset",
            "lite-2000-2050",
            "--out",
            "tmp/calendar.sqlite3",
        ]
    )
    assert args.command == "export-sqlite"
    assert args.preset == "lite-2000-2050"
    assert args.start is None
    assert args.end is None


def test_validate_sqlite_args_are_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "validate-sqlite",
            "--sqlite",
            "tmp/calendar.sqlite3",
            "--samples",
            "5",
        ]
    )
    assert args.command == "validate-sqlite"
    assert args.sqlite == "tmp/calendar.sqlite3"
    assert args.samples == 5
