from __future__ import annotations

from datetime import date, datetime
from contextlib import contextmanager
import inspect
import os
from traceback import TracebackException
from zoneinfo import ZoneInfo

from shintoki.core.new_moon import NewMoonCalculator
from shintoki.core.solar_terms import SkyfieldPrincipalTermCalculator
from shintoki.services.debug_months import run_debug_months
from shintoki.services.debug_spans import run_debug_spans


def run_debug_compare(
    *,
    new_moon_calculator: NewMoonCalculator,
    term_calculator: SkyfieldPrincipalTermCalculator,
    year: int,
    tz: str,
    ephemeris_path: str,
    pad_days: int,
    window_mode: str,
    degrees: list[int],
    strict_expect_leap: bool = False,
) -> dict:
    spans_payload = run_debug_spans(
        new_moon_calculator=new_moon_calculator,
        term_calculator=term_calculator,
        year=year,
        pad_days=pad_days,
        degrees=degrees,
        tz=tz,
        ephemeris_path=ephemeris_path,
        only_anomalies=False,
        include_newmoons=False,
    )
    months_payload = run_debug_months(
        new_moon_calculator=new_moon_calculator,
        term_calculator=term_calculator,
        year=year,
        pad_days=pad_days,
        degrees=degrees,
        tz=tz,
        ephemeris_path=ephemeris_path,
        only_anomalies=False,
        strict_expect_leap=strict_expect_leap,
        window_mode=window_mode,
    )

    shintoki_spans = _normalize_spans_for_compare(spans_payload["spans"], tz=tz)
    zeros = spans_payload["summary"]["zeros"]
    many = spans_payload["summary"]["many"]
    leap_spans = months_payload["summary"]["leap_spans"]
    issues = months_payload["summary"]["issues"]

    payload = {
        "year": year,
        "tz": tz,
        "ephemeris_path": ephemeris_path,
        "window_mode": window_mode,
        "pad_days": pad_days,
        "shintoki": {
            "spans_summary": spans_payload["summary"],
            "months_summary": months_payload["summary"],
            "months": months_payload["months"],
            "spans": shintoki_spans,
            "summary": {
                "span_count_raw": months_payload["summary"]["span_count_raw"],
                "span_count_normalized": months_payload["summary"]["span_count_normalized"],
                "zeros": zeros,
                "many": many,
                "leap_spans": leap_spans,
                "issues": issues,
            },
        },
        "jcal": probe_jcal_2033(year=year, ephemeris_path=ephemeris_path),
    }
    payload["compare_summary"] = _build_compare_summary(payload["shintoki"], payload["jcal"])
    return payload


def _build_compare_summary(shintoki: dict, jcal: dict) -> dict:
    sh_summary = shintoki.get("summary", {})
    sh_months = _normalize_month_rows(shintoki.get("months", []))

    jcal_months = _normalize_month_rows(jcal.get("months", [])) if isinstance(jcal.get("months"), list) else None
    jcal_summary = jcal.get("summary", {}) if isinstance(jcal.get("summary"), dict) else {}

    if jcal_months is None:
        return {
            "jcal_available": False,
            "jcal_reason": "jcal months info not available",
            "shintoki": {
                "span_count_normalized": sh_summary.get("span_count_normalized"),
                "zeros": sh_summary.get("zeros"),
                "many": sh_summary.get("many"),
                "leap_spans": sh_summary.get("leap_spans"),
            },
            "jcal": {
                "span_count_normalized": None,
                "zeros": None,
                "many": None,
                "leap_spans": None,
            },
            "months_match": None,
            "mismatches": [],
        }

    months_match, mismatches = _compare_month_rows(sh_months, jcal_months, limit=20)
    return {
        "jcal_available": True,
        "jcal_reason": None,
        "shintoki": {
            "span_count_normalized": sh_summary.get("span_count_normalized"),
            "zeros": sh_summary.get("zeros"),
            "many": sh_summary.get("many"),
            "leap_spans": sh_summary.get("leap_spans"),
        },
        "jcal": {
            "span_count_normalized": jcal_summary.get("span_count_normalized"),
            "zeros": jcal_summary.get("zeros"),
            "many": jcal_summary.get("many"),
            "leap_spans": jcal_summary.get("leap_spans"),
        },
        "months_match": months_match,
        "mismatches": mismatches,
    }


def _normalize_month_rows(months: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for month in months:
        rows.append(
            {
                "span_index": month.get("span_index"),
                "month_no": month.get("month_no"),
                "is_leap": month.get("is_leap"),
            }
        )
    return rows


def _compare_month_rows(
    shintoki_rows: list[dict],
    jcal_rows: list[dict],
    *,
    limit: int = 20,
) -> tuple[bool, list[dict]]:
    mismatches: list[dict] = []
    max_len = max(len(shintoki_rows), len(jcal_rows))
    for idx in range(max_len):
        sh_row = shintoki_rows[idx] if idx < len(shintoki_rows) else None
        jc_row = jcal_rows[idx] if idx < len(jcal_rows) else None
        if sh_row != jc_row and len(mismatches) < limit:
            mismatches.append({"i": idx, "shintoki": sh_row, "jcal": jc_row})
    return len(mismatches) == 0 and len(shintoki_rows) == len(jcal_rows), mismatches


def probe_jcal_2033(*, year: int, ephemeris_path: str | None = None) -> dict:
    target = date(year, 6, 10)
    try:
        with _patched_ephemeris_env(ephemeris_path):
            from jcal.core.lunisolar import gregorian_to_lunar

            kwargs = {}
            if ephemeris_path is not None:
                try:
                    sig = inspect.signature(gregorian_to_lunar)
                    if "ephemeris_path" in sig.parameters:
                        kwargs["ephemeris_path"] = ephemeris_path
                except (TypeError, ValueError):
                    pass
            result = gregorian_to_lunar(target, **kwargs)
            return {
                "ok": True,
                "target_date": target.isoformat(),
                "result": str(result),
                "error_type": None,
                "error_message": None,
                "traceback_hint": None,
            }
    except Exception as exc:  # noqa: BLE001
        tb = TracebackException.from_exception(exc)
        frame_name = tb.stack[-1].name if tb.stack else "unknown"
        return {
            "ok": False,
            "target_date": target.isoformat(),
            "result": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback_hint": f"{type(exc).__name__} at {frame_name}",
        }


def _normalize_spans_for_compare(spans: list[dict], *, tz: str) -> list[dict]:
    jst = ZoneInfo("Asia/Tokyo")
    local_tz = ZoneInfo(tz)
    rows: list[dict] = []
    for span in spans:
        start_utc = datetime.fromisoformat(span["start_utc"])
        end_utc = datetime.fromisoformat(span["end_utc"])
        rows.append(
            {
                "index": span["index"],
                "start_utc": span["start_utc"],
                "end_utc": span["end_utc"],
                "start_jst": start_utc.astimezone(jst).isoformat(),
                "end_jst": end_utc.astimezone(jst).isoformat(),
                "start_local": start_utc.astimezone(local_tz).isoformat(),
                "end_local": end_utc.astimezone(local_tz).isoformat(),
                "assigned_terms": span["zhongqi_events"],
                "flags": {
                    "ZERO": span["zhongqi_count"] == 0,
                    "MANY": span["zhongqi_count"] >= 2,
                },
            }
        )
    return rows


@contextmanager
def _patched_ephemeris_env(ephemeris_path: str | None):
    if not ephemeris_path:
        yield
        return

    keys = (
        "JCAL_EPHEMERIS_PATH",
        "JCAL_EPHEMERIS",
        "TOKI_EPHEMERIS_PATH",
        "TOKI_EPHEMERIS",
        "EPHEMERIS_PATH",
    )
    original = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ[key] = ephemeris_path
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
