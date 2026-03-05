from __future__ import annotations

from datetime import datetime

from shintoki.core.month_naming import LunarMonthSpan, build_month_naming_issues, name_lunar_months


def test_name_lunar_months_anchor_and_leap_rules() -> None:
    spans = [
        LunarMonthSpan(
            index=10,
            start_utc=datetime.fromisoformat("2033-09-01T00:00:00+00:00"),
            end_utc=datetime.fromisoformat("2033-10-01T00:00:00+00:00"),
            zhongqi_degrees=[240],
            has_zhongqi=True,
        ),
        LunarMonthSpan(
            index=11,
            start_utc=datetime.fromisoformat("2033-10-01T00:00:00+00:00"),
            end_utc=datetime.fromisoformat("2033-11-01T00:00:00+00:00"),
            zhongqi_degrees=[270],
            has_zhongqi=True,
        ),
        LunarMonthSpan(
            index=12,
            start_utc=datetime.fromisoformat("2033-11-01T00:00:00+00:00"),
            end_utc=datetime.fromisoformat("2033-12-01T00:00:00+00:00"),
            zhongqi_degrees=[],
            has_zhongqi=False,
        ),
        LunarMonthSpan(
            index=13,
            start_utc=datetime.fromisoformat("2033-12-01T00:00:00+00:00"),
            end_utc=datetime.fromisoformat("2034-01-01T00:00:00+00:00"),
            zhongqi_degrees=[300],
            has_zhongqi=True,
        ),
    ]

    named = name_lunar_months(spans, anchor_month_no=11)
    months = {m.span_index: m for m in named}

    assert months[11].month_no == 11
    assert months[12].is_leap is True
    assert months[12].month_no == 11
    assert months[13].month_no == 12


def test_name_lunar_months_strict_expect_leap_behavior_for_12_spans() -> None:
    spans: list[LunarMonthSpan] = []
    for i in range(12):
        degrees = [30 * ((i + 8) % 12)]
        has_zhongqi = True
        if i == 4:
            degrees = [270]
        if i == 8:
            degrees = []
            has_zhongqi = False
        spans.append(
            LunarMonthSpan(
                index=i,
                start_utc=datetime.fromisoformat(f"2033-{(i%12)+1:02d}-01T00:00:00+00:00"),
                end_utc=datetime.fromisoformat(f"2033-{((i+1)%12)+1:02d}-01T00:00:00+00:00"),
                zhongqi_degrees=degrees,
                has_zhongqi=has_zhongqi,
            )
        )

    non_strict = name_lunar_months(spans, strict_expect_leap=False)
    strict = name_lunar_months(spans, strict_expect_leap=True)
    non_strict_months = {m.span_index: m for m in non_strict}
    strict_months = {m.span_index: m for m in strict}
    strict_issues = build_month_naming_issues(spans, strict_expect_leap=True)

    assert non_strict_months[8].is_leap is True
    assert strict_months[8].is_leap is False
    assert strict_issues
    assert strict_issues[0]["code"] == "strict_expect_leap_conflict"
