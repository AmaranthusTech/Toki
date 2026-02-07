# src/jcal/core/month_naming.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


# 中気(0,30,...,330) → 旧暦月番号
ZHONGQI_TO_MONTHNO: dict[int, int] = {
    270: 11,  # 冬至
    300: 12,  # 大寒
    330:  1,  # 雨水
      0:  2,  # 春分
     30:  3,  # 穀雨
     60:  4,  # 小満
     90:  5,  # 夏至
    120:  6,  # 大暑
    150:  7,  # 処暑
    180:  8,  # 秋分
    210:  9,  # 霜降
    240: 10,  # 小雪
}


def _require_utc(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _jst_date(dt_utc: datetime) -> str:
    return _require_utc(dt_utc, "dt_utc").astimezone(JST).date().isoformat()


@dataclass(frozen=True)
class LunarSpan:
    """
    One lunar month span: [new_moon_utc, next_new_moon_utc)
    """
    pos: int
    new_moon_utc: datetime
    next_new_moon_utc: datetime

    def contains(self, t_utc: datetime) -> bool:
        t = _require_utc(t_utc, "t_utc")
        return self.new_moon_utc <= t < self.next_new_moon_utc

    @property
    def jst_range(self) -> str:
        a = _jst_date(self.new_moon_utc)
        b = _jst_date(self.next_new_moon_utc)
        return f"{a}..{b}"


@dataclass(frozen=True)
class NamedLunarMonth:
    """
    Result after Step5:
      month_no: 1..12
      is_leap: True if 閏月
      zhongqi_deg: 0,30,...,330 if present; None if leap-month (no zhongqi)
    """
    pos: int
    month_no: int
    is_leap: bool
    new_moon_utc: datetime
    next_new_moon_utc: datetime
    zhongqi_deg: Optional[int]
    zhongqi_utc: Optional[datetime]

    @property
    def label(self) -> str:
        if self.is_leap:
            return f"M{self.month_no:02d} (LEAP)"
        return f"M{self.month_no:02d}"

    @property
    def jst_range(self) -> str:
        a = _jst_date(self.new_moon_utc)
        b = _jst_date(self.next_new_moon_utc)
        return f"{a}..{b}"


def build_lunar_spans_from_moons(
    moons: List[datetime],
    start_span_index: int,
    span_count: int,
) -> List[LunarSpan]:
    """
    Build spans: for i in [0..span_count-1]
      span_i = [moons[start+i], moons[start+i+1])
    """
    if span_count <= 0:
        return []
    if start_span_index < 0:
        raise ValueError("start_span_index must be >=0")
    if start_span_index + span_count >= len(moons):
        raise ValueError("moons range too short for requested spans")

    out: List[LunarSpan] = []
    for pos in range(span_count):
        i = start_span_index + pos
        out.append(
            LunarSpan(
                pos=pos,
                new_moon_utc=_require_utc(moons[i], "new_moon_utc"),
                next_new_moon_utc=_require_utc(moons[i + 1], "next_new_moon_utc"),
            )
        )
    return out


def assign_month_names_by_zhongqi(
    spans: List[LunarSpan],
    zhongqi_events: Iterable[Tuple[float, datetime]],
    *,
    leap_span_pos: Optional[int],
    mode: str = "tenpo",
) -> List[NamedLunarMonth]:
    """
    Step5 (month naming by principal terms / 中気)

    - For each span, find principal-term events (0,30,...,330) inside it
    - month_no is determined by zhongqi_deg via ZHONGQI_TO_MONTHNO
    - leap span has no zhongqi -> month_no inherits from previous month

    mode
    ----
    "tenpo" (default):
      - strict: non-leap span must contain exactly ONE zhongqi
      - multiple zhongqi in one span -> error
      - leap span must contain NONE -> error if contained

    "ws_first" (冬至優先モード / 案1寄せ):
      - allow multiple zhongqi in one span
      - if 270(冬至) is present, choose it
      - otherwise choose the earliest zhongqi in that span
      - leap span must still contain NONE (leap判定はStep4側で合わせる前提)

        Notes on containment
        -------------------
        Step4 (leap判定) と同じく、JST日付境界で span への帰属を判定する。
        判定基準: span_start_day <= term_day < span_end_day
        （参照データとの整合性を優先）
    """
    if mode not in ("tenpo", "ws_first"):
        raise ValueError(f"unknown mode={mode!r} (expected 'tenpo' or 'ws_first')")

    # index zhongqi by time for quick lookup
    zq: List[Tuple[int, datetime]] = []
    for deg_f, t in zhongqi_events:
        deg_i = int(round(float(deg_f))) % 360
        # keep only principal terms
        if deg_i % 30 != 0:
            continue
        zq.append((deg_i, _require_utc(t, "zhongqi_time")))
    zq.sort(key=lambda x: x[1])

    def _zhongqi_hits_in_span(span: LunarSpan) -> List[Tuple[int, datetime]]:
        """
        Collect all zhongqi hits inside the span using JST day-basis containment.

        Rule (JST day-basis):
          span_start_day <= term_day < span_end_day
        """
        s_day = span.new_moon_utc.astimezone(JST).date()
        e_day = span.next_new_moon_utc.astimezone(JST).date()

        hits: List[Tuple[int, datetime]] = []
        for deg_i, t in zq:
            t_day = t.astimezone(JST).date()
            if s_day <= t_day < e_day:
                hits.append((deg_i, t))

        hits.sort(key=lambda x: x[1])
        return hits

    def _choose_hit(span_pos: int, hits: List[Tuple[int, datetime]]) -> Optional[Tuple[int, datetime]]:
        if not hits:
            return None

        if mode == "tenpo":
            if len(hits) >= 2:
                raise RuntimeError(
                    f"Multiple zhongqi in one span pos={span_pos}: "
                    + ", ".join(f"{d}@{t.isoformat()}" for d, t in hits)
                )
            return hits[0]

        # ws_first: 冬至優先（案1）
        for deg_i, t in hits:
            if deg_i == 270:
                return (deg_i, t)
        return hits[0]

    out: List[NamedLunarMonth] = []

    prev_month_no: Optional[int] = None
    for span in spans:
        is_leap = (leap_span_pos is not None and span.pos == leap_span_pos)

        hits = _zhongqi_hits_in_span(span)
        chosen = _choose_hit(span.pos, hits)

        if is_leap:
            # Leap month must have no zhongqi; if it has, your Step4 is wrong.
            if chosen is not None:
                raise RuntimeError(
                    f"Leap span pos={span.pos} unexpectedly contains zhongqi deg={chosen[0]} at {chosen[1].isoformat()} "
                    f"(mode={mode})"
                )
            if prev_month_no is None:
                raise RuntimeError("First span cannot be leap month (no previous month_no)")
            month_no = prev_month_no
            out.append(
                NamedLunarMonth(
                    pos=span.pos,
                    month_no=month_no,
                    is_leap=True,
                    new_moon_utc=span.new_moon_utc,
                    next_new_moon_utc=span.next_new_moon_utc,
                    zhongqi_deg=None,
                    zhongqi_utc=None,
                )
            )
            continue

        # Non-leap month: must have zhongqi
        if chosen is None:
            raise RuntimeError(
                f"Non-leap span pos={span.pos} has no zhongqi. "
                f"(If this is actually a leap month, your leap_span_pos is wrong.) "
                f"(mode={mode})"
            )

        deg_i, t = chosen
        if deg_i not in ZHONGQI_TO_MONTHNO:
            raise RuntimeError(f"Unexpected zhongqi deg={deg_i} in span pos={span.pos} (mode={mode})")

        month_no = ZHONGQI_TO_MONTHNO[deg_i]
        out.append(
            NamedLunarMonth(
                pos=span.pos,
                month_no=month_no,
                is_leap=False,
                new_moon_utc=span.new_moon_utc,
                next_new_moon_utc=span.next_new_moon_utc,
                zhongqi_deg=deg_i,
                zhongqi_utc=t,
            )
        )
        prev_month_no = month_no

    return out