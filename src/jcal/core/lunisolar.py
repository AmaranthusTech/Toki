# src/jcal/core/lunisolar.py
from __future__ import annotations

import os
import sys

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from functools import lru_cache
from bisect import bisect_right
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo

from .astronomy import AstronomyEngine
from .config import NewMoonConfig, SolarTermConfig, LuniSolarConfig
from .providers.skyfield_provider import SkyfieldProvider
from .solstice_anchor import solstice_anchors_for_years, saisjitsu_window_for_year
from .leap_month import lunar_spans_between_anchor_indices, decide_leap_month, PrincipalTerm
from .solarterms import principal_terms_between
from .month_naming import LunarSpan, assign_month_names_by_zhongqi, NamedLunarMonth

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc


# ============================================================
# env helpers
# ============================================================

def _env_truthy(name: str) -> bool:
    v = os.environ.get(name, "")
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _debug_enabled() -> bool:
    return _env_truthy("JCAL_DEBUG_LUNISOLAR")


def _test_print_enabled() -> bool:
    return _env_truthy("JCAL_TEST_PRINT")


def _debug_window() -> tuple[date, date] | None:
    fr = os.environ.get("JCAL_DEBUG_FROM", "").strip()
    to = os.environ.get("JCAL_DEBUG_TO", "").strip()
    if not fr or not to:
        return None
    return (date.fromisoformat(fr), date.fromisoformat(to))


def _debug_print(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _leap_epsilon_seconds_default() -> int:
    """
    端点丸め事故が出る環境向けに微調整できるようにする。
    例: JCAL_LEAP_EPSILON_SECONDS=1
    """
    v = os.environ.get("JCAL_LEAP_EPSILON_SECONDS", "").strip()
    try:
        return int(v) if v else 0
    except Exception:
        return 0


# ============================================================
# span / term helpers
# ============================================================

def _span_bounds_utc(sp: LunarSpan) -> Tuple[datetime, datetime]:
    """
    LunarSpan の実装差分に対応して (start_utc, end_utc) を取り出す。
    """
    # よくある候補
    candidates = [
        ("start_utc", "end_utc"),
        ("start", "end"),
        ("t0_utc", "t1_utc"),
        ("begin_utc", "end_utc"),
        ("begin", "end"),
        ("start_dt_utc", "end_dt_utc"),
    ]
    for a, b in candidates:
        if hasattr(sp, a) and hasattr(sp, b):
            s0 = getattr(sp, a)
            s1 = getattr(sp, b)
            if isinstance(s0, datetime) and isinstance(s1, datetime):
                return s0.astimezone(UTC), s1.astimezone(UTC)

    # 新月境界で持ってるケース（よくある）
    if hasattr(sp, "new_moon_utc") and hasattr(sp, "next_new_moon_utc"):
        s0 = getattr(sp, "new_moon_utc")
        s1 = getattr(sp, "next_new_moon_utc")
        if isinstance(s0, datetime) and isinstance(s1, datetime):
            return s0.astimezone(UTC), s1.astimezone(UTC)

    raise AttributeError(
        f"LunarSpan bounds not found. Available attrs: {sorted([x for x in dir(sp) if not x.startswith('_')])}"
    )


def _terms_in_span_left_closed(
    s_utc: datetime,
    e_utc: datetime,
    zhongqi_events: List[Tuple[float, datetime]],
    *,
    epsilon_seconds: int = 0,
) -> List[Tuple[int, datetime]]:
    """
    month_naming / Step4 と同じく、JST日付境界で span への帰属を判定する。
    判定基準: span_start_day <= term_day < span_end_day
    （epsilon_seconds は互換用だが、JST day-basis では通常使わない）
    """
    _ = epsilon_seconds  # day-basis では未使用（互換のため残す）
    s_day = s_utc.astimezone(JST).date()
    e_day = e_utc.astimezone(JST).date()

    out: List[Tuple[int, datetime]] = []
    for deg, t in zhongqi_events:
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        else:
            t = t.astimezone(UTC)
        deg_i = int(round(float(deg))) % 360
        t_day = t.astimezone(JST).date()
        if s_day <= t_day < e_day:
            out.append((deg_i, t))
    out.sort(key=lambda x: x[1])
    return out


def _resolve_leap_span_pos_for_month_naming(
    spans2: List[LunarSpan],
    zhongqi_events: List[Tuple[float, datetime]],
    *,
    expect_leap: bool,
    epsilon_seconds: int = 0,
    spans2_offset: Optional[int] = None,
) -> Optional[int]:
    """
    Step4 の結果が month_naming の境界判定とズレることがあるので、
    「spans2 + zhongqi_events」を month_naming と同じ見え方で数えて
    leap_span_pos を確定する。

    期待仕様:
      - 閏年(13 spans)なら「中気ゼロの span がちょうど1個」
      - 平年なら「中気ゼロの span が0個」
    """
    zeros: List[int] = []
    many: List[int] = []

    for i, sp in enumerate(spans2):
        s_utc, e_utc = _span_bounds_utc(sp)
        inside = _terms_in_span_left_closed(s_utc, e_utc, zhongqi_events, epsilon_seconds=epsilon_seconds)
        if len(inside) == 0:
            zeros.append(i)
        elif len(inside) >= 2:
            many.append(i)

    if _debug_enabled():
        zeros_abs = [int(spans2_offset) + i for i in zeros] if spans2_offset is not None else []
        many_abs = [int(spans2_offset) + i for i in many] if spans2_offset is not None else []
        _debug_print(
            f"[JCAL_DEBUG_LUNISOLAR] zhongqi_distribution(L): "
            f"zeros(pos)={zeros} zeros(abs)={zeros_abs} "
            f"many(pos)={many} many(abs)={many_abs} "
            f"expect_leap={expect_leap} spans2_len={len(spans2)} spans2_offset={spans2_offset}"
        )

    if many:
        raise RuntimeError(f"zhongqi_count>=2 spans found (boundary mismatch?): {many}")

    if expect_leap:
        if len(zeros) != 1:
            raise RuntimeError(f"expect_leap=True but zero-zhongqi spans={zeros} (count={len(zeros)})")
        return zeros[0]

    if len(zeros) != 0:
        raise RuntimeError(f"expect_leap=False but zero-zhongqi spans={zeros}")
    return None


def _in_debug_window_by_span_jst(s_utc: datetime, e_utc: datetime) -> bool:
    win = _debug_window()
    if win is None:
        return True
    d0 = s_utc.astimezone(JST).date()
    d1 = (e_utc - timedelta(seconds=1)).astimezone(JST).date()
    return (win[0] <= d1) and (d0 < win[1])


def _debug_dump_spans(
    *,
    year: int,
    spans2: List[LunarSpan],
    zq: List[Tuple[float, datetime]],
    named: List[NamedLunarMonth],
    leap_span_pos: Optional[int],
    spans2_offset: Optional[int] = None,
) -> None:
    if not _debug_enabled():
        return

    # window 指定があるなら、「この spans2 自体の期間」が window と交差するかで判定する
    win = _debug_window()
    if win is not None:
        if not spans2:
            return
        s0, _ = _span_bounds_utc(spans2[0])
        _, s1 = _span_bounds_utc(spans2[-1])
        if not _in_debug_window_by_span_jst(s0, s1):
            return

    leap_abs = (int(spans2_offset) + int(leap_span_pos)) if (spans2_offset is not None and leap_span_pos is not None) else None
    _debug_print(
        f"[JCAL_DEBUG_LUNISOLAR] year={year} "
        f"leap_span_pos(pos)={leap_span_pos} leap_span_pos(abs)={leap_abs} "
        f"spans2_offset={spans2_offset}"
    )

    eps = _leap_epsilon_seconds_default()

    for i, sp in enumerate(spans2):
        s0, s1 = _span_bounds_utc(sp)
        nm = named[i] if i < len(named) else None

        terms = _terms_in_span_left_closed(s0, s1, zq, epsilon_seconds=eps)

        def fmt_terms(xs: List[Tuple[int, datetime]]) -> str:
            if not xs:
                return "-"
            return ", ".join(f"{deg_i:03d}@{t.astimezone(JST).isoformat()}" for deg_i, t in xs)

        start_j = s0.astimezone(JST).isoformat()
        end_j = s1.astimezone(JST).isoformat()

        abs_i = (int(spans2_offset) + i) if spans2_offset is not None else None
        span_label = f"span[pos={i:02d} abs={abs_i}]" if abs_i is not None else f"span[pos={i:02d}]"

        if nm is None:
            _debug_print(
                f"  {span_label} {start_j} .. {end_j}  named=None  zq={fmt_terms(terms)}"
            )
            continue

        _debug_print(
            f"  {span_label} {start_j} .. {end_j}  "
            f"month_no={int(nm.month_no):02d} is_leap={bool(nm.is_leap)}  "
            f"new_moon={nm.new_moon_utc.astimezone(JST).isoformat()}  "
            f"zq={fmt_terms(terms)}"
        )


# ============================================================
# Engine cache
# ============================================================

@lru_cache(maxsize=4)
def _engine_for(ephemeris: Optional[Union[str, Path]], ephemeris_path: Optional[Path]) -> AstronomyEngine:
    provider = SkyfieldProvider(ephemeris=ephemeris, ephemeris_path=ephemeris_path)
    return AstronomyEngine(provider=provider)


@lru_cache(maxsize=1)
def _default_engine() -> AstronomyEngine:
    return _engine_for(None, None)


# ============================================================
# Public types
# ============================================================

@dataclass(frozen=True)
class LunarDate:
    """
    旧暦の「月・日・閏」のみ（既存）
    """
    month: int
    day: int
    is_leap: bool


@dataclass(frozen=True)
class LunarYMD:
    """
    旧暦の「年・月・日・閏」（APIで欲しいやつ）
    """
    year: int
    month: int
    day: int
    is_leap: bool


# ============================================================
# Core utilities
# ============================================================

def _jst_sample_dt(d_jst: date, sample_policy: str) -> datetime:
    if sample_policy == "noon":
        return datetime.combine(d_jst, time(12, 0), tzinfo=JST)
    if sample_policy == "end":
        return datetime.combine(d_jst, time(23, 59, 59), tzinfo=JST)
    raise ValueError(f"sample_policy must be 'noon' or 'end' (got {sample_policy!r})")


def _jst_date(dt_utc: datetime) -> date:
    return dt_utc.astimezone(JST).date()


# ============================================================
# Cache structures
# ============================================================

@dataclass(frozen=True)
class _LuniSolarRangeCache:
    months: List[NamedLunarMonth]  # 時系列
    month_starts: List[datetime]   # months[i].new_moon_utc の配列（bisect用）


def _build_named_months_for_year(
    eng: AstronomyEngine,
    year: int,
    *,
    newmoon_config: NewMoonConfig,
    solarterm_config: SolarTermConfig,
    lunisolar_config: LuniSolarConfig,
) -> List[NamedLunarMonth]:
    """
    year の歳実区間 (year winter-solstice anchor -> year+1 anchor) の月一覧を構築
    """
    start_utc = datetime(year - 1, 1, 1, tzinfo=UTC)
    end_utc   = datetime(year + 2, 1, 1, tzinfo=UTC)

    moons, anchors = solstice_anchors_for_years(
        eng, start_utc, end_utc,
        years=[year, year + 1],
        newmoon_config=newmoon_config,
        solarterm_config=solarterm_config,
        lunisolar_config=lunisolar_config,
    )

    w = saisjitsu_window_for_year(anchors, year)

    # spans（12 or 13）
    spans = lunar_spans_between_anchor_indices(
        moons,
        w.start_anchor.span_index,
        w.end_anchor.span_index,
    )
    if not spans:
        raise RuntimeError("spans empty (unexpected)")

    # principal terms（中気）を spans の範囲に必要なだけ拾う
    pad = int(getattr(lunisolar_config, "term_pad_days", getattr(lunisolar_config, "term_pad_days", 40)))
    if pad <= 0:
        pad = 40

    t0 = spans[0].start_utc.astimezone(UTC) - timedelta(days=pad)
    t1 = spans[-1].end_utc.astimezone(UTC) + timedelta(days=pad)

    zq = principal_terms_between(
        eng, t0, t1,
        config=solarterm_config,
        degrees=[0.0] + [float(x) for x in range(30, 360, 30)],
    )

    # Step4（従来通り）
    terms_for_step4 = []
    for (deg, t) in zq:
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        else:
            t = t.astimezone(UTC)
        terms_for_step4.append(PrincipalTerm(deg=int(round(deg)) % 360, instant_utc=t))

    dec = decide_leap_month(spans, terms_for_step4, anchor_month_no=11)

    # Step5 に渡す spans2（posズレ防止で spans と同一境界）
    spans2: List[LunarSpan] = [
        LunarSpan(
            pos=i,
            new_moon_utc=sp.start_utc.astimezone(UTC),
            next_new_moon_utc=sp.end_utc.astimezone(UTC),
        )
        for i, sp in enumerate(spans)
    ]
    spans2_offset = spans[0].index if spans else None

    # ★ここが今回の核心：month_naming と同じ基準で leap_span_pos を確定する
    expect_leap = (len(spans2) == 13)
    eps = _leap_epsilon_seconds_default()
    leap_span_pos_final = _resolve_leap_span_pos_for_month_naming(
        spans2,
        zhongqi_events=zq,
        expect_leap=expect_leap,
        epsilon_seconds=eps,
        spans2_offset=spans2_offset,
    )

    if _debug_enabled():
        s0 = spans2[0].new_moon_utc
        s1 = spans2[-1].next_new_moon_utc
        if _in_debug_window_by_span_jst(s0, s1):
            step4_pos = dec.leap_span_pos
            step4_abs = (spans2_offset + step4_pos) if (spans2_offset is not None and step4_pos is not None) else None
            final_pos = leap_span_pos_final
            final_abs = (spans2_offset + final_pos) if (spans2_offset is not None and final_pos is not None) else None
            no_zh_pos = dec.no_zhongqi_positions
            no_zh_abs = [spans2_offset + i for i in no_zh_pos] if spans2_offset is not None else []
            _debug_print(
                f"[JCAL_DEBUG_LUNISOLAR] year={year} span_count={len(spans)} "
                f"spans2_offset={spans2_offset} "
                f"leap_span_pos(step4,pos)={step4_pos} leap_span_pos(step4,abs)={step4_abs} -> "
                f"leap_span_pos(final,pos)={final_pos} leap_span_pos(final,abs)={final_abs} "
                f"no_zh(step4,pos)={no_zh_pos} no_zh(step4,abs)={no_zh_abs}"
            )

    mode = os.environ.get("JCAL_MONTH_NAMING_MODE", "ws_first").strip().lower()

    named = assign_month_names_by_zhongqi(
        spans2,
        zhongqi_events=zq,
        leap_span_pos=leap_span_pos_final,
        mode=mode,
    )

    _debug_dump_spans(
        year=year,
        spans2=spans2,
        zq=zq,
        named=named,
        leap_span_pos=leap_span_pos_final,
        spans2_offset=spans2_offset,
    )

    return named


def build_range_cache(
    start: date,
    end: date,
    *,
    sample_policy: str = "noon",
    eng: Optional[AstronomyEngine] = None,
    ephemeris: Optional[Union[str, Path]] = None,
    ephemeris_path: Optional[Path] = None,
    newmoon_config: NewMoonConfig = NewMoonConfig(),
    solarterm_config: SolarTermConfig = SolarTermConfig(),
    lunisolar_config: LuniSolarConfig = LuniSolarConfig(),
) -> _LuniSolarRangeCache:
    """
    [start, end) をカバーする NamedLunarMonth をまとめて作って保持
    """
    if not (start < end):
        return _LuniSolarRangeCache(months=[], month_starts=[])

    if eng is None:
        if ephemeris is None and ephemeris_path is None:
            eng = _default_engine()
        else:
            eng = _engine_for(ephemeris, ephemeris_path)

    years = list(range(start.year - 1, end.year + 2))

    months_all: List[NamedLunarMonth] = []
    for y in years:
        months_all.extend(
            _build_named_months_for_year(
                eng, y,
                newmoon_config=newmoon_config,
                solarterm_config=solarterm_config,
                lunisolar_config=lunisolar_config,
            )
        )

    months_all.sort(key=lambda m: m.new_moon_utc)
    dedup: List[NamedLunarMonth] = []
    last_start: Optional[datetime] = None
    for m in months_all:
        if last_start is None or m.new_moon_utc != last_start:
            dedup.append(m)
            last_start = m.new_moon_utc

    starts = [m.new_moon_utc for m in dedup]
    return _LuniSolarRangeCache(months=dedup, month_starts=starts)


def to_lunar_date(
    d_jst: date,
    *,
    sample_policy: str = "noon",
    cache: Optional[_LuniSolarRangeCache] = None,
) -> LunarDate:
    """
    日付→旧暦（高速版）。
    cache を渡せば O(log N) で引ける。
    """
    t_jst = _jst_sample_dt(d_jst, sample_policy)
    t_utc = t_jst.astimezone(UTC)

    if cache is None:
        cache = build_range_cache(
            d_jst - timedelta(days=40),
            d_jst + timedelta(days=40),
            sample_policy=sample_policy,
        )

    i = bisect_right(cache.month_starts, t_utc) - 1
    if i < 0 or i >= len(cache.months):
        raise RuntimeError("date out of cached range; expand cache window")

    m = cache.months[i]
    day = (_jst_sample_dt(d_jst, sample_policy).date() - _jst_date(m.new_moon_utc)).days + 1
    return LunarDate(month=int(m.month_no), day=int(day), is_leap=bool(m.is_leap))


def lunar_dates_between(
    start: date,
    end: date,
    *,
    sample_policy: str = "noon",
    ephemeris: Optional[Union[str, Path]] = None,
    ephemeris_path: Optional[Path] = None,
) -> Iterable[Tuple[date, LunarDate]]:
    """
    まとめて変換：キャッシュを1回作って日々を引く
    """
    cache = build_range_cache(
        start, end,
        sample_policy=sample_policy,
        ephemeris=ephemeris,
        ephemeris_path=ephemeris_path,
    )
    d = start
    while d < end:
        yield d, to_lunar_date(d, sample_policy=sample_policy, cache=cache)
        d += timedelta(days=1)


# ============================================================
# New: gregorian_to_lunar (year/month/day/is_leap)
# ============================================================

def _lunar_year_for_date(
    d_jst: date,
    *,
    cache: _LuniSolarRangeCache,
    tz: ZoneInfo = JST,
) -> int:
    """
    旧暦年を「直近の旧暦1月（平月）の開始日」から確定する。

    - cache.months は時系列の NamedLunarMonth
    - (month_no == 1 and not is_leap) の new_moon_utc を JST に直して、
      それが d_jst 以下の最大のものを採用する
    """
    candidates: List[date] = []
    for m in cache.months:
        if int(m.month_no) == 1 and (not bool(m.is_leap)):
            candidates.append(m.new_moon_utc.astimezone(tz).date())

    if not candidates:
        raise RuntimeError("cannot determine lunar year: no month_no=1 found in cache; expand cache window")

    candidates.sort()
    # d_jst 以下の最大
    i = bisect_right(candidates, d_jst) - 1
    if i < 0:
        raise RuntimeError("cannot determine lunar year: date is before cached lunar new year; expand cache window")

    # 旧暦年番号は「その旧暦元日の属する西暦年」で返す（API用）
    # ※ここは仕様として固定。必要なら後で「旧暦年ラベル」も別途持てる
    return int(candidates[i].year)


def gregorian_to_lunar(
    d_jst: date,
    *,
    sample_policy: str = "end",
    cache: Optional[_LuniSolarRangeCache] = None,
    cache_padding_days: int = 400,
) -> LunarYMD:
    """
    西暦(JST日付) → 旧暦(年/月/日/閏)

    - month/day/is_leap: to_lunar_date() の結果
    - year: 直近の旧暦1月開始日（平月）から確定

    cache を渡すと高速。
    cache が None の場合は、年確定のために広めにキャッシュを作る（デフォ400日）。
    """
    if cache is None:
        pad = int(cache_padding_days)
        if pad < 40:
            pad = 40
        cache = build_range_cache(
            d_jst - timedelta(days=pad),
            d_jst + timedelta(days=60),
            sample_policy=sample_policy,
        )

    ld = to_lunar_date(d_jst, sample_policy=sample_policy, cache=cache)
    y = _lunar_year_for_date(d_jst, cache=cache, tz=JST)

    return LunarYMD(
        year=int(y),
        month=int(ld.month),
        day=int(ld.day),
        is_leap=bool(ld.is_leap),
    )


def gregorian_to_lunar_between(
    start: date,
    end: date,
    *,
    sample_policy: str = "end",
    cache_padding_days: int = 400,
) -> Iterable[Tuple[date, LunarYMD]]:
    """
    [start, end) をまとめて西暦→旧暦(年/月/日/閏)に変換する。

    - キャッシュは1回だけ作る（高速）
    - year 確定のために start より前にも余裕を持たせる（デフォ400日）
    """
    if not (start < end):
        return []

    pad = int(cache_padding_days)
    if pad < 40:
        pad = 40

    cache = build_range_cache(
        start - timedelta(days=pad),
        end + timedelta(days=60),
        sample_policy=sample_policy,
    )

    out: List[Tuple[date, LunarYMD]] = []
    d = start
    while d < end:
        out.append((d, gregorian_to_lunar(d, sample_policy=sample_policy, cache=cache)))
        d += timedelta(days=1)
    return out