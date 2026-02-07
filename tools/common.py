from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Tuple

DEFAULT_TZ = "Asia/Tokyo"
DEFAULT_DAY_BASIS = "jst"
DEFAULT_EPHEMERIS = "de440s.bsp"

ENV_EPHEMERIS = "TOKI_EPHEMERIS"
ENV_EPHEMERIS_PATH = "TOKI_EPHEMERIS_PATH"


@dataclass(frozen=True)
class EphemerisConfig:
    name: str
    path: Optional[Path]
    skip_reason: Optional[str]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    parser.add_argument("--tz", default=DEFAULT_TZ)
    parser.add_argument("--day-basis", default=DEFAULT_DAY_BASIS)
    parser.add_argument("--ephemeris", default="")
    parser.add_argument("--ephemeris-path", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def iter_dates(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


def resolve_ephemeris(name_arg: str, path_arg: str) -> EphemerisConfig:
    name = (name_arg or "").strip() or os.environ.get(ENV_EPHEMERIS, "").strip() or DEFAULT_EPHEMERIS

    path_raw = (path_arg or "").strip() or os.environ.get(ENV_EPHEMERIS_PATH, "").strip()
    if path_raw:
        p = Path(path_raw).expanduser()
        if p.exists():
            return EphemerisConfig(name=name, path=p, skip_reason=None)
        return EphemerisConfig(name=name, path=None, skip_reason=f"ephemeris_path not found: {p}")

    local = Path("data") / name
    if local.exists():
        return EphemerisConfig(name=name, path=local, skip_reason=None)

    return EphemerisConfig(
        name=name,
        path=None,
        skip_reason=(
            "ephemeris not found. set TOKI_EPHEMERIS_PATH or provide --ephemeris-path, "
            "or place data/<ephemeris>."
        ),
    )


def resolve_date_range(args: argparse.Namespace) -> Tuple[Optional[date], Optional[date]]:
    if args.start and args.end:
        return parse_date(args.start), parse_date(args.end)
    if args.date:
        d = parse_date(args.date)
        return d, d
    return None, None


def dump_json(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def skip(msg: str) -> None:
    print(f"SKIP: {msg}")
    sys.exit(0)
