from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from shintoki.core.month_naming import (
    LunarMonthSpan,
    build_month_naming_issues,
    find_anchor_span_index,
    name_lunar_months,
)
from shintoki.core.new_moon import NewMoonCalculator, NewMoonWindowRequest, year_window_utc
from shintoki.core.solar_terms import (
    PrincipalTermEvent,
    PrincipalTermWindowRequest,
    SkyfieldPrincipalTermCalculator,
)
from shintoki.services.debug_spans import assign_terms_to_spans, build_spans


def run_debug_months(
    *,
    new_moon_calculator: NewMoonCalculator,
    term_calculator: SkyfieldPrincipalTermCalculator,
    year: int,
    pad_days: int,
    degrees: list[int],
    tz: str,
    ephemeris_path: str,
    only_anomalies: bool = False,
    strict_expect_leap: bool = False,
    window_mode: str = "calendar-year",
) -> dict:
    start_utc, end_utc = year_window_utc(year, pad_days)
    new_moons = new_moon_calculator.find_new_moons_between(
        NewMoonWindowRequest(
            tz=tz,
            ephemeris_path=ephemeris_path,
            start_utc=start_utc,
            end_utc=end_utc,
        )
    )
    spans = build_spans(new_moons)

    term_events: list[tuple[int, PrincipalTermEvent]] = []
    for degree in degrees:
        events = term_calculator.find_events_between(
            PrincipalTermWindowRequest(
                degree=degree,
                tz=tz,
                ephemeris_path=ephemeris_path,
                start_utc=start_utc,
                end_utc=end_utc,
            )
        )
        term_events.extend((degree, event) for event in events)

    span_payloads = assign_terms_to_spans(spans, term_events)
    terms_by_degree = _group_terms_by_degree(term_events)
    normalized_spans, normalization_note, normalization_issues = normalize_spans(
        span_payloads,
        terms_by_degree,
        year=year,
        window_mode=window_mode,
        tz=tz,
    )
    lunar_spans = [_to_lunar_month_span(span) for span in normalized_spans]
    named_months = name_lunar_months(
        lunar_spans,
        anchor_month_no=11,
        strict_expect_leap=strict_expect_leap,
    )

    leap_spans = [month.span_index for month in named_months if month.is_leap]
    zero_spans = [span.index for span in lunar_spans if not span.has_zhongqi]
    anchor_span_index = find_anchor_span_index(lunar_spans)
    issues = build_month_naming_issues(lunar_spans, strict_expect_leap=strict_expect_leap)
    if strict_expect_leap and window_mode == "raw":
        issues.append(
            {
                "code": "strict_raw_window_notice",
                "message": "strict_expect_leap in raw mode may not hit 12/13 span assumptions.",
            }
        )
    issues.extend(normalization_issues)
    anchor_span_payload = _find_span_payload(normalized_spans, anchor_span_index)
    anchor_term_utc = _find_anchor_term_utc(anchor_span_payload)

    months_payload = []
    for month in named_months:
        item = asdict(month)
        item["start_utc"] = month.start_utc.isoformat()
        item["end_utc"] = month.end_utc.isoformat()
        months_payload.append(item)

    if only_anomalies:
        months_payload = [m for m in months_payload if m["is_leap"]]

    return {
        "year": year,
        "tz": tz,
        "ephemeris_path": ephemeris_path,
        "search_window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
        },
        "months": months_payload,
        "summary": {
            "anchor_span_index": anchor_span_index,
            "anchor_term_utc": anchor_term_utc,
            "anchor_span_start_utc": anchor_span_payload.get("start_utc") if anchor_span_payload else None,
            "anchor_span_end_utc": anchor_span_payload.get("end_utc") if anchor_span_payload else None,
            "span_count_raw": len(span_payloads),
            "span_count_normalized": len(normalized_spans),
            "window_mode": window_mode,
            "normalization_note": normalization_note,
            "normalization_issues": normalization_issues,
            "months_count": len(named_months),
            "leap_spans": leap_spans,
            "zero_spans": zero_spans,
            "issues": issues,
        },
        "status": "ok",
    }


def _to_lunar_month_span(span_payload: dict) -> LunarMonthSpan:
    return LunarMonthSpan(
        index=span_payload["index"],
        start_utc=datetime.fromisoformat(span_payload["start_utc"]),
        end_utc=datetime.fromisoformat(span_payload["end_utc"]),
        zhongqi_degrees=list(span_payload["zhongqi_degrees"]),
        has_zhongqi=span_payload["zhongqi_count"] > 0,
        start_local_date=span_payload.get("start_local_date"),
        end_local_date_exclusive=span_payload.get("end_local_date_exclusive"),
    )


def normalize_spans(
    spans: list[dict],
    terms_by_degree: dict[int, list[PrincipalTermEvent]],
    *,
    year: int,
    window_mode: str,
    tz: str,
) -> tuple[list[dict], str, list[dict[str, str]]]:
    del terms_by_degree

    issues: list[dict[str, str]] = []
    if window_mode == "raw":
        return spans, "raw mode: no normalization", issues

    if window_mode == "calendar-year":
        tzinfo = ZoneInfo(tz)
        y0 = datetime(year, 1, 1, tzinfo=tzinfo)
        y1 = datetime(year + 1, 1, 1, tzinfo=tzinfo)
        filtered = []
        for span in spans:
            start = datetime.fromisoformat(span["start_utc"]).astimezone(tzinfo)
            end = datetime.fromisoformat(span["end_utc"]).astimezone(tzinfo)
            if start < y1 and end > y0:
                filtered.append(span)
        note = f"calendar-year overlap [{y0.isoformat()}, {y1.isoformat()})"
        if len(filtered) not in (12, 13):
            issues.append(
                {
                    "code": "normalized_span_count_unexpected",
                    "message": f"calendar-year normalized spans={len(filtered)} (expected 12 or 13)",
                }
            )
        return filtered, note, issues

    if window_mode == "solstice-to-solstice":
        y0 = datetime(year, 1, 1, tzinfo=timezone.utc)
        anchor_positions = []
        for pos, span in enumerate(spans):
            if 270 in span.get("zhongqi_degrees", []):
                anchor_positions.append(pos)
        if not anchor_positions:
            issues.append(
                {
                    "code": "no_solstice_anchor",
                    "message": "no span contains deg=270 for solstice-to-solstice normalization",
                }
            )
            return spans, "fallback to raw due to missing solstice anchor", issues

        start_pos = anchor_positions[0]
        for pos in anchor_positions:
            term_utc = _find_anchor_term_utc(spans[pos]) or spans[pos]["start_utc"]
            if datetime.fromisoformat(term_utc) <= y0:
                start_pos = pos
        next_positions = [p for p in anchor_positions if p > start_pos]
        if not next_positions:
            issues.append(
                {
                    "code": "next_solstice_anchor_missing",
                    "message": "could not find next deg=270 anchor span; using tail window",
                }
            )
            normalized = spans[start_pos:]
            note = f"solstice-to-solstice from span#{spans[start_pos]['index']} to end"
        else:
            end_pos = next_positions[0]
            normalized = spans[start_pos:end_pos]
            note = (
                f"solstice-to-solstice span#{spans[start_pos]['index']} "
                f"to span#{spans[end_pos]['index']} (exclusive)"
            )

        if len(normalized) not in (12, 13):
            issues.append(
                {
                    "code": "normalized_span_count_unexpected",
                    "message": f"solstice-to-solstice normalized spans={len(normalized)} (expected 12 or 13)",
                }
            )
        return normalized, note, issues

    issues.append({"code": "unknown_window_mode", "message": f"unsupported window_mode: {window_mode}"})
    return spans, "fallback to raw due to unsupported window_mode", issues


def _group_terms_by_degree(
    term_events: list[tuple[int, PrincipalTermEvent]],
) -> dict[int, list[PrincipalTermEvent]]:
    grouped: dict[int, list[PrincipalTermEvent]] = {}
    for degree, event in term_events:
        grouped.setdefault(degree, []).append(event)
    return grouped


def _find_span_payload(span_payloads: list[dict], span_index: int | None) -> dict | None:
    if span_index is None:
        return None
    for span in span_payloads:
        if span["index"] == span_index:
            return span
    return None


def _find_anchor_term_utc(anchor_span_payload: dict | None) -> str | None:
    if not anchor_span_payload:
        return None
    for event in anchor_span_payload.get("zhongqi_events", []):
        if event.get("deg") == 270:
            return event.get("utc")
    return None
