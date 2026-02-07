from __future__ import annotations

"""
Rokuyo check script.

Uses:
- jcal.core.lunisolar.gregorian_to_lunar
- jcal.features.config.rokuyo_from_lunar_month_day
"""

import argparse
from datetime import timedelta

from jcal.core.lunisolar import build_range_cache, gregorian_to_lunar
from jcal.features.config import rokuyo_from_lunar_month_day

from tools.common import add_common_args, resolve_date_range, resolve_ephemeris, dump_json, skip


def main() -> None:
    parser = argparse.ArgumentParser(description="Rokuyo (六曜) check")
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
    while cur <= end:
        l = gregorian_to_lunar(cur, sample_policy="end", cache=cache)
        r = rokuyo_from_lunar_month_day(int(l.month), int(l.day))

        if args.json:
            rows.append(
                {
                    "date": cur.isoformat(),
                    "lunar": {
                        "month": int(l.month),
                        "day": int(l.day),
                        "leap": bool(l.is_leap),
                    },
                    "rokuyo": r,
                }
            )
        else:
            if args.verbose:
                print(
                    f"{cur.isoformat()}  rokuyo={r}  "
                    f"lunar={int(l.month):02d}/{int(l.day):02d} leap={bool(l.is_leap)}"
                )
            else:
                print(f"{cur.isoformat()}  {r}")

        cur = cur + timedelta(days=1)

    if args.json:
        dump_json({"rows": rows})


if __name__ == "__main__":
    main()
