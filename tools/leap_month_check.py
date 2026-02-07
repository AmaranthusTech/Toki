from __future__ import annotations

"""
Leap month check script.

Uses:
- jcal.core.solstice_anchor.solstice_anchors_for_years / saisjitsu_window_for_year
- jcal.core.leap_month.decide_leap_month / spans_with_zhongqi / assign_month_numbers
- jcal.core.solarterms.principal_terms_between
"""

import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from jcal.core.astronomy import AstronomyEngine
from jcal.core.config import SolarTermConfig
from jcal.core.leap_month import (
    PrincipalTerm,
    assign_month_numbers,
    decide_leap_month,
    lunar_spans_between_anchor_indices,
    spans_with_zhongqi,
)
from jcal.core.providers.skyfield_provider import SkyfieldProvider
from jcal.core.solarterms import principal_terms_between
from jcal.core.solstice_anchor import solstice_anchors_for_years, saisjitsu_window_for_year
from jcal.features.config import lunar_month_display_name

from tools.common import add_common_args, resolve_date_range, resolve_ephemeris, dump_json, skip

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")


def _years_from_args(args, start, end) -> list[int]:
    if args.year:
        return [int(args.year)]
    if start and end:
        return list(range(start.year, end.year + 1))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Leap month (閏月) check")
    add_common_args(parser)
    parser.add_argument("--year", type=int, help="target year (Gregorian)")
    args = parser.parse_args()

    start, end = resolve_date_range(args)
    years = _years_from_args(args, start, end)
    if not years:
        parser.error("--year or --date or --start/--end required")

    eph = resolve_ephemeris(args.ephemeris, args.ephemeris_path)
    if eph.skip_reason:
        skip(eph.skip_reason)

    eng = AstronomyEngine(provider=SkyfieldProvider(ephemeris=eph.name, ephemeris_path=eph.path))
    cfg = SolarTermConfig()

    out_rows = []
    for year in years:
        start_utc = datetime(year - 1, 1, 1, tzinfo=UTC)
        end_utc = datetime(year + 2, 1, 1, tzinfo=UTC)

        moons, anchors = solstice_anchors_for_years(eng, start_utc, end_utc, years=[year, year + 1])
        w = saisjitsu_window_for_year(anchors, year)
        spans = lunar_spans_between_anchor_indices(moons, w.start_anchor.span_index, w.end_anchor.span_index)

        if not spans:
            continue

        t0 = spans[0].start_utc.astimezone(UTC) - timedelta(days=40)
        t1 = spans[-1].end_utc.astimezone(UTC) + timedelta(days=40)
        zq = principal_terms_between(
            eng,
            t0,
            t1,
            config=cfg,
            degrees=[float(x) for x in range(0, 360, 30)],
        )
        terms = [PrincipalTerm(deg=int(round(float(deg))) % 360, instant_utc=t) for (deg, t) in zq]

        dec = decide_leap_month(spans, terms, anchor_month_no=11)
        labels = assign_month_numbers(len(spans), leap_span_pos=dec.leap_span_pos, anchor_month_no=11)

        leap_info = None
        if dec.leap_span_pos is not None:
            leap_month_no = labels[dec.leap_span_pos].month_no
            leap_info = {
                "pos": int(dec.leap_span_pos),
                "month_no": int(leap_month_no),
                "month_name": lunar_month_display_name(int(leap_month_no), True),
            }

        row = {
            "year": int(year),
            "span_count": int(len(spans)),
            "leap": leap_info,
            "no_zhongqi_positions": dec.no_zhongqi_positions,
        }

        if args.verbose:
            has_zh = spans_with_zhongqi(spans, terms)
            no_zh = [i for i, v in enumerate(has_zh) if not v]
            row["no_zh_summary"] = no_zh
            row["span_ranges_jst"] = [
                {
                    "pos": i,
                    "start_jst": s.start_utc.astimezone(JST).isoformat(),
                    "end_jst": s.end_utc.astimezone(JST).isoformat(),
                }
                for i, s in enumerate(spans)
            ]

        out_rows.append(row)

        if not args.json:
            if leap_info is None:
                print(f"{year}: leap=none span_count={len(spans)}")
            else:
                print(
                    f"{year}: leap_pos={leap_info['pos']} month_no={leap_info['month_no']} "
                    f"month_name={leap_info['month_name']} span_count={len(spans)}"
                )
            if args.verbose:
                print(f"  no_zh={row.get('no_zh_summary', [])}")

    if args.json:
        dump_json({"years": out_rows})


if __name__ == "__main__":
    main()
