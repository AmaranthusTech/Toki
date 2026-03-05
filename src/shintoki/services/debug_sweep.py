from __future__ import annotations

from shintoki.core.new_moon import NewMoonCalculator
from shintoki.core.solar_terms import SkyfieldPrincipalTermCalculator
from shintoki.services.debug_compare import run_debug_compare


def run_debug_sweep(
    *,
    new_moon_calculator: NewMoonCalculator,
    term_calculator: SkyfieldPrincipalTermCalculator,
    start_year: int,
    end_year: int,
    tz: str,
    ephemeris_path: str,
    pad_days: int,
    window_mode: str,
    degrees: list[int],
    strict_expect_leap: bool = False,
) -> dict:
    years_payload: list[dict] = []
    total = 0
    sh_ok_count = 0
    jcal_ok_count = 0
    months_match_count = 0

    for year in range(start_year, end_year + 1):
        total += 1
        compared = run_debug_compare(
            new_moon_calculator=new_moon_calculator,
            term_calculator=term_calculator,
            year=year,
            tz=tz,
            ephemeris_path=ephemeris_path,
            pad_days=pad_days,
            window_mode=window_mode,
            degrees=degrees,
            strict_expect_leap=strict_expect_leap,
        )

        sh_summary = compared["shintoki"]["summary"]
        jcal = compared["jcal"]
        compare_summary = compared.get("compare_summary", {})
        issues_count = len(sh_summary.get("issues", []))
        sh_ok = issues_count == 0
        jcal_ok = bool(jcal.get("ok"))
        months_match = compare_summary.get("months_match")

        if sh_ok:
            sh_ok_count += 1
        if jcal_ok:
            jcal_ok_count += 1
        if months_match is True:
            months_match_count += 1

        years_payload.append(
            {
                "year": year,
                "shintoki": {
                    "span_count_normalized": sh_summary.get("span_count_normalized"),
                    "zeros": sh_summary.get("zeros"),
                    "many": sh_summary.get("many"),
                    "leap_spans": sh_summary.get("leap_spans"),
                    "issues_count": issues_count,
                },
                "jcal": {
                    "ok": jcal_ok,
                    "error_type": None if jcal_ok else jcal.get("error_type"),
                },
                "compare_summary": {
                    "months_match": months_match,
                },
            }
        )

    return {
        "start_year": start_year,
        "end_year": end_year,
        "window_mode": window_mode,
        "strict_expect_leap": strict_expect_leap,
        "years": years_payload,
        "summary": {
            "total": total,
            "ok_count": sh_ok_count,
            "jcal_ok_count": jcal_ok_count,
            "months_match_count": months_match_count,
        },
    }
