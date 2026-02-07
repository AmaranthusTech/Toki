from __future__ import annotations

"""
Sekki24 (24節気) check script.

Uses:
- jcal.core.solarterms.principal_terms_between
- jcal.features.config.sekki_info_from_deg
"""

import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from jcal.core.astronomy import AstronomyEngine
from jcal.core.config import SolarTermConfig
from jcal.core.providers.skyfield_provider import SkyfieldProvider
from jcal.core.solarterms import principal_terms_between
from jcal.features.config import SEKKI24_DEGS, sekki_info_from_deg

from tools.common import add_common_args, resolve_date_range, resolve_ephemeris, dump_json, skip

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sekki24 (24節気) check")
    add_common_args(parser)
    parser.add_argument("--daily", action="store_true", help="list daily sekki names in range")
    args = parser.parse_args()

    start, end = resolve_date_range(args)
    if start is None or end is None:
        parser.error("--date or --start/--end required")

    eph = resolve_ephemeris(args.ephemeris, args.ephemeris_path)
    if eph.skip_reason:
        skip(eph.skip_reason)

    eng = AstronomyEngine(provider=SkyfieldProvider(ephemeris=eph.name, ephemeris_path=eph.path))
    cfg = SolarTermConfig()

    t0 = datetime(start.year, start.month, start.day, tzinfo=UTC) - timedelta(days=2)
    t1 = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=2)

    raw = principal_terms_between(
        eng,
        t0,
        t1,
        config=cfg,
        degrees=[float(x) for x in SEKKI24_DEGS],
    )

    rows = []
    for deg, t in raw:
        info = sekki_info_from_deg(float(deg))
        at_jst = t.astimezone(JST)
        if not (start <= at_jst.date() <= end):
            continue
        rows.append(
            {
                "name": info.name,
                "degree": int(info.deg),
                "kind": info.kind,
                "at_jst": at_jst.isoformat(),
                "date_jst": at_jst.date().isoformat(),
            }
        )

    rows.sort(key=lambda x: x["at_jst"])

    if args.json:
        payload = {"sekki": rows}
        if args.daily:
            daily = {}
            for r in rows:
                daily.setdefault(r["date_jst"], []).append(r["name"])
            payload["daily"] = daily
        dump_json(payload)
        return

    for r in rows:
        print(f"{r['date_jst']}  {r['name']}  {r['kind']}  deg={r['degree']:03d}  at={r['at_jst']}")

    if args.daily:
        print("\n# Daily summary")
        daily = {}
        for r in rows:
            daily.setdefault(r["date_jst"], []).append(r["name"])
        for d in sorted(daily.keys()):
            print(f"{d}  {'／'.join(daily[d])}")


if __name__ == "__main__":
    main()
