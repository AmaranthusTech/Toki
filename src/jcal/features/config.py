# src/jcal/features/config.py
from __future__ import annotations

"""
Feature-level configuration / constants.

- 二十四節気 (sekki24): 0..345 deg (15-deg step) => name / kind(節|中気) / n(0..23)
- 六曜 (rokuyo): lunar month/day => label

Design goals:
- Accept float degree inputs robustly (e.g., 284.999999, 285.0) and normalize safely.
- Keep mapping stable and test-friendly (n parity => kind).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

# ============================================================
# 二十四節気 (24 solar terms)
#   NOTE:
#     This project defines n:
#       n = (deg_norm / 15) % 24
#     kind:
#       n even  -> 中気 (principal term)
#       n odd   -> 節   (minor term)
#
#     This matches your test expectations:
#       - n even => deg % 30 == 0
#       - n odd  => deg % 30 == 15
# ============================================================

SEKKI24: List[Tuple[int, str]] = [
    (0,   "春分"),
    (15,  "清明"),
    (30,  "穀雨"),
    (45,  "立夏"),
    (60,  "小満"),
    (75,  "芒種"),
    (90,  "夏至"),
    (105, "小暑"),
    (120, "大暑"),
    (135, "立秋"),
    (150, "処暑"),
    (165, "白露"),
    (180, "秋分"),
    (195, "寒露"),
    (210, "霜降"),
    (225, "立冬"),
    (240, "小雪"),
    (255, "大雪"),
    (270, "冬至"),
    (285, "小寒"),
    (300, "大寒"),
    (315, "立春"),
    (330, "雨水"),
    (345, "啓蟄"),
]

LUNAR_MONTH_NAME_BY_MONTH_NO: Dict[int, str] = {
    1:  "一月",
    2:  "二月",
    3:  "三月",
    4:  "四月",
    5:  "五月",
    6:  "六月",
    7:  "七月",
    8:  "八月",
    9:  "九月",
    10: "十月",
    11: "十一月",
    12: "十二月",
}

SEKKI24_DEGS: List[int] = [deg for deg, _ in SEKKI24]
SEKKI24_NAME_BY_DEG: Dict[int, str] = {deg: name for deg, name in SEKKI24}


def normalize_sekki_deg(deg: float) -> int:
    """
    Normalize arbitrary degree value into one of:
      0, 15, 30, ..., 345 (int)
    """
    d = float(deg) % 360.0
    # nearest 15-deg bin
    k = int(round(d / 15.0)) % 24
    return k * 15


def sekki_n_from_deg(deg: float) -> int:
    """
    Return sekki index n in [0..23].
    n = deg_norm / 15
    """
    deg_norm = normalize_sekki_deg(deg)
    return int((deg_norm // 15) % 24)


def sekki_kind_from_n(n: int) -> str:
    """
    Return "中気" if n is even, else "節".
    """
    nn = int(n) % 24
    return "中気" if (nn % 2 == 0) else "節"


def sekki_kind_from_deg(deg: float) -> str:
    """
    Convenience: determine kind from degree by normalized n parity.
    """
    return sekki_kind_from_n(sekki_n_from_deg(deg))


def sekki_name_from_deg(deg: float) -> str:
    """
    Get sekki name from degree (float OK).
    """
    deg_norm = normalize_sekki_deg(deg)
    try:
        return SEKKI24_NAME_BY_DEG[deg_norm]
    except KeyError as e:
        raise KeyError(f"Unknown sekki degree after normalization: deg={deg} -> {deg_norm}") from e


def lunar_month_name_from_month_no(month_no: int) -> str:
    m = int(month_no)
    try:
        return LUNAR_MONTH_NAME_BY_MONTH_NO[m]
    except KeyError as e:
        raise ValueError(f"invalid lunar month_no: {month_no}") from e

def lunar_month_display_name(month_no: int, is_leap: bool) -> str:
    base = lunar_month_name_from_month_no(month_no)
    return f"閏{base}" if is_leap else base


@dataclass(frozen=True)
class SekkiInfo:
    """
    Structured info for a sekki degree.
    """
    n: int
    deg: int
    kind: str
    name: str


def sekki_info_from_deg(deg: float) -> SekkiInfo:
    """
    Produce normalized info bundle for a given (possibly float) degree.
    """
    deg_norm = normalize_sekki_deg(deg)
    n = int((deg_norm // 15) % 24)
    kind = sekki_kind_from_n(n)
    name = SEKKI24_NAME_BY_DEG[deg_norm]
    return SekkiInfo(n=n, deg=deg_norm, kind=kind, name=name)

# ============================================================
# 六曜 (rokuyo)
#   Spec (手順どおり):
#     R = (M + D) % 6
#     R=2：先勝
#     R=3：友引
#     R=4：先負
#     R=5：仏滅
#     R=0：大安
#     R=1：赤口
#
#   Notes:
#   - 閏月でも月番号はそのまま（閏5月も 5月として扱う）
#   - 旧暦 1/1 は (1+1)%6=2 => 先勝 で必ず始まる
# ============================================================

ROKUYO_BY_R: Dict[int, str] = {
    0: "大安",
    1: "赤口",
    2: "先勝",
    3: "友引",
    4: "先負",
    5: "仏滅",
}


def rokuyo_r_from_lunar_month_day(lunar_month: int, lunar_day: int) -> int:
    """
    R = (M + D) % 6 を返す。
    """
    m = int(lunar_month)
    d = int(lunar_day)
    if not (1 <= m <= 12):
        raise ValueError(f"lunar_month out of range: {m}")
    if not (1 <= d <= 30):
        raise ValueError(f"lunar_day out of range: {d}")
    return (m + d) % 6


def rokuyo_from_lunar_month_day(lunar_month: int, lunar_day: int) -> str:
    """
    旧暦の月日から六曜を求める（手順どおり）:
      R = (M + D) % 6
      R の表で六曜を返す
    """
    r = rokuyo_r_from_lunar_month_day(lunar_month, lunar_day)
    return ROKUYO_BY_R[r]