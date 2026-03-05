from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LunarMonthSpan:
    index: int
    start_utc: datetime
    end_utc: datetime
    zhongqi_degrees: list[int]
    has_zhongqi: bool
    start_local_date: str | None = None
    end_local_date_exclusive: str | None = None


@dataclass(frozen=True)
class NamedLunarMonth:
    span_index: int
    month_no: int
    is_leap: bool
    start_utc: datetime
    end_utc: datetime
    has_zhongqi: bool
    zhongqi_degrees: list[int]
    start_local_date: str | None = None
    end_local_date_exclusive: str | None = None


def name_lunar_months(
    spans: list[LunarMonthSpan],
    *,
    anchor_month_no: int = 11,
    strict_expect_leap: bool = False,
) -> list[NamedLunarMonth]:
    if not spans:
        return []

    leap_span_indices = _resolve_leap_span_indices(spans, strict_expect_leap=strict_expect_leap)
    anchor_pos = next((i for i, s in enumerate(spans) if 270 in s.zhongqi_degrees), 0)
    nonleap_flags = [0 if span.index in leap_span_indices else 1 for span in spans]
    prefix_nonleap = [0]
    for flag in nonleap_flags:
        prefix_nonleap.append(prefix_nonleap[-1] + flag)

    def nonleap_count(start: int, end: int) -> int:
        return prefix_nonleap[end + 1] - prefix_nonleap[start]

    named: list[NamedLunarMonth] = []
    for pos, span in enumerate(spans):
        if pos > anchor_pos:
            delta = nonleap_count(anchor_pos + 1, pos)
        elif pos < anchor_pos:
            delta = -nonleap_count(pos + 1, anchor_pos)
        else:
            delta = 0
        month_no = _shift_month_no(anchor_month_no, delta)
        named.append(
            NamedLunarMonth(
                span_index=span.index,
                month_no=month_no,
                is_leap=span.index in leap_span_indices,
                start_utc=span.start_utc,
                end_utc=span.end_utc,
                has_zhongqi=span.has_zhongqi,
                zhongqi_degrees=span.zhongqi_degrees,
                start_local_date=span.start_local_date,
                end_local_date_exclusive=span.end_local_date_exclusive,
            )
        )

    return named


def find_anchor_span_index(spans: list[LunarMonthSpan]) -> int | None:
    for span in spans:
        if 270 in span.zhongqi_degrees:
            return span.index
    return spans[0].index if spans else None


def _shift_month_no(base: int, delta: int) -> int:
    return ((base - 1 + delta) % 12) + 1


def build_month_naming_issues(
    spans: list[LunarMonthSpan],
    *,
    strict_expect_leap: bool = False,
) -> list[dict[str, str]]:
    if not strict_expect_leap:
        return []

    issues: list[dict[str, str]] = []
    zero_indices = [span.index for span in spans if not span.has_zhongqi]
    span_count = len(spans)
    if span_count == 12 and zero_indices:
        issues.append(
            {
                "code": "strict_expect_leap_conflict",
                "message": (
                    "strict_expect_leap=True with 12 spans found zero-zhongqi spans: "
                    f"{zero_indices}. leap month assignment is suppressed."
                ),
            }
        )
    return issues


def _resolve_leap_span_indices(
    spans: list[LunarMonthSpan],
    *,
    strict_expect_leap: bool,
) -> set[int]:
    zero_indices = {span.index for span in spans if not span.has_zhongqi}
    if not strict_expect_leap:
        return zero_indices

    span_count = len(spans)
    if span_count == 13:
        return zero_indices
    if span_count == 12:
        return set()
    return zero_indices
