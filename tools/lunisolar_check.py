from __future__ import annotations

"""
Lunisolar check script.

Uses:
- jcal.core.lunisolar.gregorian_to_lunar
- jcal.features.config.lunar_month_display_name
"""

import argparse
from datetime import date, timedelta

from jcal.core.lunisolar import build_range_cache, gregorian_to_lunar
from jcal.features.config import lunar_month_display_name

from tools.common import add_common_args, resolve_date_range, resolve_ephemeris, dump_json, skip


def _format_label(month: int, day: int, is_leap: bool) -> str:
    return f"{'閏' if is_leap else ''}{month:02d}/{day:02d}"


def _format_month_label(month: int, is_leap: bool) -> str:
    return f"{'閏' if is_leap else ''}{month:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lunisolar (旧暦) check")
    add_common_args(parser)
    args = parser.parse_args()

    start, end = resolve_date_range(args)
    if start is None or end is None:
        parser.error("--date or --start/--end required")

    eph = resolve_ephemeris(args.ephemeris, args.ephemeris_path)
    if eph.skip_reason:
        skip(eph.skip_reason)

    cache = build_range_cache(
        start,
        end + timedelta(days=1),
        sample_policy="end",
        ephemeris=eph.name,
        ephemeris_path=eph.path,
    )

    rows = []
    cur = start
    prev_month = None
    while cur <= end:
        l = gregorian_to_lunar(cur, sample_policy="end", cache=cache)
        month_name = lunar_month_display_name(int(l.month), bool(l.is_leap))
        label = _format_label(int(l.month), int(l.day), bool(l.is_leap))
        month_label = _format_month_label(int(l.month), bool(l.is_leap))

        if args.json:
            rows.append(
                {
                    "date": cur.isoformat(),
                    "year": int(l.year),
                    "month": int(l.month),
                    "day": int(l.day),
                    "leap": bool(l.is_leap),
                    "month_label": month_label,
                    "label": label,
                    "month_name": month_name,
                }
            )
        else:
            sep = ""
            if prev_month is not None and int(l.day) == 1:
                sep = "\n"
            print(
                f"{sep}{cur.isoformat()}  L={label}  "
                f"year={int(l.year)} month_name={month_name}"
            )
        prev_month = (int(l.month), bool(l.is_leap))
        cur = cur + timedelta(days=1)

    if args.json:
        dump_json({"rows": rows})


if __name__ == "__main__":
    main()
