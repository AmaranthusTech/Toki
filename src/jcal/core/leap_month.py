# src/jcal/core/leap_month.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from bisect import bisect_right
from typing import Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# ============================
# Data models
# ============================

@dataclass(frozen=True)
class LunarSpan:
    """
    One lunisolar month span: [start_new_moon, next_new_moon)
    """
    index: int                 # global index in moons[]
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class PrincipalTerm:
    """
    A principal term event (中気): solar longitude multiple of 30°.
    deg is normalized to {0,30,...,330}.
    """
    deg: int
    instant_utc: datetime


@dataclass(frozen=True)
class MonthLabel:
    month_no: int              # 1..12, and 11 is anchor month at winter solstice
    is_leap: bool              # True if this span is the leap month


@dataclass(frozen=True)
class LeapDecision:
    """
    Step4 output:
      - leap_span_pos: 0-based position within the 13 spans (None if non-leap year)
      - no_zhongqi_positions: list of span positions that have no principal term
    """
    leap_span_pos: Optional[int]
    no_zhongqi_positions: List[int]


# ============================
# UTC helpers
# ============================

def _require_utc(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)



# --- 追加：中気(30°倍)だけに絞る ---
def _only_zhongqi_terms(terms: Iterable[PrincipalTerm]) -> List[PrincipalTerm]:
    """
    閏月判定に使うのは「中気」だけ（30°刻み）に限定する。
    24節気(15°刻み)が混ざると「無中気月」判定が壊れる可能性がある。
    """
    out: List[PrincipalTerm] = []
    for e in terms:
        deg = int(e.deg) % 360
        if deg % 30 == 0:
            out.append(PrincipalTerm(deg=deg, instant_utc=_require_utc(e.instant_utc, "term.instant_utc")))
    out.sort(key=lambda x: x.instant_utc)
    return out


# --- 追加：冬至(270°)スパン判定をUTC厳密に ---
def _find_winter_solstice_span_pos_utc(
    spans: Sequence[LunarSpan],
    terms: Iterable[PrincipalTerm],
) -> Optional[int]:
    """
    270°(冬至) が入っている span を UTC境界で厳密に探す。
    閏月判定ロジック側はUTC厳密で統一する。
    """
    for e in terms:
        if int(e.deg) % 360 != 270:
            continue
        pos = _term_pos_in_spans(spans, e.instant_utc)
        if pos is not None:
            return pos
    return None


# --- 追加：デバッグ用（どのspanにどの中気が入ってるか見える化） ---
def _debug_dump_spans_and_terms(spans: Sequence[LunarSpan], terms: Sequence[PrincipalTerm]) -> None:
    print("[JCAL_DEBUG_LUNISOLAR] spans:")
    for i, s in enumerate(spans):
        sj = s.start_utc.astimezone(JST)
        ej = s.end_utc.astimezone(JST)
        print(
            f"  span[pos={i} abs={s.index}] start_utc={s.start_utc.isoformat()} end_utc={s.end_utc.isoformat()} "
            f"start_jst={sj.isoformat()} end_jst={ej.isoformat()} "
            f"start_jst_date={sj.date()} end_jst_date={ej.date()}"
        )
        inside = _terms_in_span_utc(s, terms)
        if inside:
            for t in inside:
                tj = t.instant_utc.astimezone(JST)
                print(
                    f"    term deg={t.deg:03d} utc={t.instant_utc.isoformat()} jst={tj.isoformat()} jst_date={tj.date()}"
                )
        else:
            print("    (no zhongqi terms in this span)")
            
# ============================
# Span building
# ============================

def lunar_spans_between_anchor_indices(
    moons: Sequence[datetime],
    start_span_index: int,
    end_span_index: int,
) -> List[LunarSpan]:
    """
    Build lunar spans using moons[i]..moons[i+1] for i in [start_span_index, end_span_index).

    If start_span_index is anchor.span_index (month11 span),
    and end_span_index is next_anchor.span_index,
    then number of spans is end_span_index - start_span_index (12 or 13 typically).
    """
    if end_span_index <= start_span_index:
        return []
    if start_span_index < 0 or end_span_index >= len(moons):
        raise ValueError("span indices out of moons range")

    out: List[LunarSpan] = []
    for i in range(start_span_index, end_span_index):
        out.append(
            LunarSpan(
                index=i,
                start_utc=_require_utc(moons[i], "moons[i]"),
                end_utc=_require_utc(moons[i + 1], "moons[i+1]"),
            )
        )
    return out

def _term_pos_in_spans(spans: Sequence[LunarSpan], t_utc: datetime) -> Optional[int]:
    t = _require_utc(t_utc, "t_utc")
    if not spans:
        return None

    # spans は start_utc 昇順のはず
    starts = [s.start_utc for s in spans]
    i = bisect_right(starts, t) - 1
    if i < 0:
        return None

    if spans[i].start_utc <= t < spans[i].end_utc:
        return i
    return None

# ============================
# Zhongqi presence (中気を含むか)
# ============================
def _term_pos_in_spans_daybasis(
    spans: Sequence[LunarSpan],
    t_utc: datetime,
    *,
    tz: ZoneInfo = JST,
) -> Optional[int]:
    """
    day-basis (暦日境界) で term を spans に割り当てる。
    判定基準: span_start_day <= term_day < span_end_day
    """
    t = _require_utc(t_utc, "t_utc")
    term_day = t.astimezone(tz).date()

    for i, s in enumerate(spans):
        start_day = s.start_utc.astimezone(tz).date()
        end_day = s.end_utc.astimezone(tz).date()
        if start_day <= term_day < end_day:
            return i
    return None

def spans_with_zhongqi(
    spans: Sequence[LunarSpan],
    terms: Iterable[PrincipalTerm],
) -> List[bool]:
    """
    For each span, True if it contains at least one principal term.
    判定は day-basis (JST日付境界) に統一する。
    """
    has = [False] * len(spans)
    for e in terms:
        pos = _term_pos_in_spans_daybasis(spans, e.instant_utc, tz=JST)
        if pos is not None:
            has[pos] = True
    return has


def _terms_in_span_utc(span: LunarSpan, terms: Iterable[PrincipalTerm]) -> List[PrincipalTerm]:
    """
    UTC境界で厳密に span 内に入ってる中気を集める（例外判定用/デバッグ用）
    """
    a = _require_utc(span.start_utc, "span.start_utc")
    b = _require_utc(span.end_utc, "span.end_utc")
    out: List[PrincipalTerm] = []
    for e in terms:
        t = _require_utc(e.instant_utc, "term.instant_utc")
        if a <= t < b:
            out.append(e)
    out.sort(key=lambda x: x.instant_utc)
    return out

def _find_winter_solstice_span_pos(
    spans: Sequence[LunarSpan],
    terms: Iterable[PrincipalTerm],
) -> Optional[int]:
    """
    270°(冬至) が入っている span を JST日付境界で探す。

    判定基準:
      span_start_day <= term_day < span_end_day

    NOTE:
      spans_with_zhongqi() / month_naming.py と同じ基準に揃える。
      2033問題みたいな境界付近のズレを防ぐため、UTC厳密ではなく
      旧暦実装側の「暦日」ルールに寄せる。
    """
    # 冬至(270°)の時刻候補を拾う（範囲外でもOK、span側で振り分け）
    ws_terms: List[datetime] = []
    for e in terms:
        if e.deg == 270:
            ws_terms.append(_require_utc(e.instant_utc, "term.instant_utc"))

    if not ws_terms:
        return None

    ws_terms.sort()

    hit_pos: Optional[int] = None
    for ws_utc in ws_terms:
        ws_day = ws_utc.astimezone(JST).date()

        for i, s in enumerate(spans):
            start_day = s.start_utc.astimezone(JST).date()
            end_day = s.end_utc.astimezone(JST).date()

            if start_day <= ws_day < end_day:
                if hit_pos is not None and hit_pos != i:
                    raise RuntimeError(
                        f"Winter solstice matched multiple spans: {hit_pos} and {i} "
                        f"(ws={ws_utc.isoformat()}, ws_day={ws_day})"
                    )
                hit_pos = i

    return hit_pos

# ============================
# Month numbering simulator
# ============================

def assign_month_numbers(
    span_count: int,
    *,
    leap_span_pos: Optional[int],
    anchor_month_no: int = 11,
) -> List[MonthLabel]:
    """
    Assign month numbers to spans.
    Rules:
      - span 0 is anchor_month_no (winter-solstice month => 11).
      - normally each next span increments month number (wrap 12->1).
      - leap span repeats previous month number and does NOT advance the cycle.
    """
    if span_count <= 0:
        return []

    labels: List[MonthLabel] = []
    cur = int(anchor_month_no)

    for pos in range(span_count):
        if pos == 0:
            labels.append(MonthLabel(month_no=cur, is_leap=False))
            continue

        if leap_span_pos is not None and pos == leap_span_pos:
            labels.append(MonthLabel(month_no=cur, is_leap=True))
        else:
            cur = 1 if cur == 12 else (cur + 1)
            labels.append(MonthLabel(month_no=cur, is_leap=False))

    return labels


# ============================
# Constraint scoring (二至二分)
# ============================

def _build_key_term_positions(
    spans: Sequence[LunarSpan],
    terms: Iterable[PrincipalTerm],
) -> dict[int, int]:
    want = {0, 90, 180, 270}
    out: dict[int, int] = {}
    for e in terms:
        if e.deg not in want:
            continue
        pos = _term_pos_in_spans_daybasis(spans, e.instant_utc, tz=JST)
        if pos is None:
            continue
        out.setdefault(e.deg, pos)
    return out


def _constraints_satisfied(
    labels: Sequence[MonthLabel],
    key_positions: dict[int, int],
    *,
    anchor_month_no: int = 11,
) -> Tuple[bool, int]:
    score = 0
    desired = {270: anchor_month_no, 0: 2, 90: 5, 180: 8}

    ok = True
    for deg, want_month in desired.items():
        pos = key_positions.get(deg)
        if pos is None:
            continue
        got = labels[pos].month_no
        if got == want_month:
            score += 1
        else:
            ok = False
    return ok, score


# ============================
# Step4 decision
# ============================

def decide_leap_month(
    spans: Sequence[LunarSpan],
    terms: Iterable[PrincipalTerm],
    *,
    anchor_month_no: int = 11,
) -> LeapDecision:
    span_count = len(spans)

    # ★超重要：閏月判定は「中気(30°倍)」だけを見る
    zh_terms = _only_zhongqi_terms(terms)

    has_zh = spans_with_zhongqi(spans, zh_terms)
    no_zh = [i for i, v in enumerate(has_zh) if not v]

    if os.getenv("JCAL_DEBUG_LUNISOLAR") == "1":
        spans_offset = spans[0].index if spans else None
        no_zh_abs = [spans[i].index for i in no_zh] if spans else []
        span_index_range = (
            f"{spans[0].index}..{spans[-1].index}"
            if spans
            else "-"
        )
        print(
            f"[JCAL_DEBUG_LUNISOLAR] span_count={span_count} "
            f"span_index_offset={spans_offset} span_index_range={span_index_range} "
            f"no_zh(pos)={no_zh} no_zh(abs)={no_zh_abs}"
        )
        _debug_dump_spans_and_terms(spans, zh_terms)

    # Non-leap year shortcut
    if span_count == 12:
        return LeapDecision(leap_span_pos=None, no_zhongqi_positions=no_zh)

    if span_count != 13:
        return LeapDecision(leap_span_pos=(no_zh[0] if no_zh else None), no_zhongqi_positions=no_zh)

    # ---- Special rule trigger ----
    if len(no_zh) == 3:
        # ★冬至スパンもUTC厳密に揃える
        ws_pos = _find_winter_solstice_span_pos_utc(spans, zh_terms)
        if ws_pos is not None and (ws_pos + 1) < span_count:
            leap_pos = ws_pos + 1

            if has_zh[leap_pos] is False:
                if os.getenv("JCAL_DEBUG_LUNISOLAR") == "1":
                    print(f"[JCAL_DEBUG_LUNISOLAR] special(13 & no_zh=3): ws_pos={ws_pos} -> leap_span_pos={leap_pos}")
                return LeapDecision(leap_span_pos=leap_pos, no_zhongqi_positions=no_zh)

            if os.getenv("JCAL_DEBUG_LUNISOLAR") == "1":
                print(
                    f"[JCAL_DEBUG_LUNISOLAR] special rule wanted leap_pos={leap_pos} but has_zh=True; fallback to canonical."
                )

    # Key-term constraints helper（★ここも中気だけでOK。0/90/180/270は全部30°倍なので）
    key_pos = _build_key_term_positions(spans, zh_terms)

    # canonical: choose among no-zhongqi
    if len(no_zh) == 1:
        return LeapDecision(leap_span_pos=no_zh[0], no_zhongqi_positions=no_zh)

    if len(no_zh) >= 2:
        best: Optional[int] = None
        for cand in no_zh:
            labels = assign_month_numbers(span_count, leap_span_pos=cand, anchor_month_no=anchor_month_no)
            ok, _score = _constraints_satisfied(labels, key_pos, anchor_month_no=anchor_month_no)
            if ok:
                best = cand
                break
        if best is None:
            best = no_zh[0]
        return LeapDecision(leap_span_pos=best, no_zhongqi_positions=no_zh)

    # rare: 13 spans but all have zhongqi -> brute force
    best_cand: Optional[int] = None
    best_ok = False
    best_score = -1

    for cand in range(0, span_count):
        labels = assign_month_numbers(span_count, leap_span_pos=cand, anchor_month_no=anchor_month_no)
        ok, score = _constraints_satisfied(labels, key_pos, anchor_month_no=anchor_month_no)

        if ok and not best_ok:
            best_ok = True
            best_score = score
            best_cand = cand
        elif ok and best_ok:
            if best_cand is None or cand < best_cand:
                best_cand = cand
        elif (not best_ok) and score > best_score:
            best_score = score
            best_cand = cand

    return LeapDecision(leap_span_pos=best_cand, no_zhongqi_positions=no_zh)