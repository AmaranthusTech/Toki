# src/jcal/features/rokuyo.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Union

from jcal.core.lunisolar import LunarDate, to_lunar_date
from jcal.features.config import (
    rokuyo_from_lunar_month_day,
    rokuyo_r_from_lunar_month_day,
)


@dataclass(frozen=True)
class Rokuyo:
    """
    六曜の計算結果（デバッグ/テストしやすいように構造体で持たせる）。

    - r: (M + D) % 6 の値
    - label: 六曜ラベル（先勝/友引/先負/仏滅/大安/赤口）
    """
    r: int
    label: str

    def __str__(self) -> str:
        return self.label


def rokuyo_from_lunar_date(ld: LunarDate) -> str:
    """
    旧暦 (LunarDate) から六曜ラベルを返す。

    NOTE:
      - 閏月でも月番号はそのまま（閏5月も 5月として扱う）
      - 仕様は features/config.py の rokuyo_from_lunar_month_day に完全準拠
    """
    return rokuyo_from_lunar_month_day(ld.month, ld.day)


def rokuyo_info_from_lunar_date(ld: LunarDate) -> Rokuyo:
    """
    旧暦 (LunarDate) から六曜の詳細（r と label）を返す。
    """
    r = rokuyo_r_from_lunar_month_day(ld.month, ld.day)
    label = rokuyo_from_lunar_month_day(ld.month, ld.day)
    return Rokuyo(r=r, label=label)


def rokuyo_for_date(
    d_jst: date,
    *,
    sample_policy: str = "noon",
    ephemeris: Optional[Union[str, Path]] = None,
    ephemeris_path: Optional[Path] = None,
) -> str:
    """
    JST日付から六曜を返す（内部で旧暦を引いてから六曜化）。

    - sample_policy は core と同じ（"noon" or "end"）
    - ephemeris / ephemeris_path は lunisolar 側に渡せるようにしておく
      （de440s.bsp を使いたいテスト等で便利）
    """
    ld = to_lunar_date(
        d_jst,
        sample_policy=sample_policy,
        cache=None,  # 単発変換なら core 側が適切に短いキャッシュを作る
    )
    # NOTE: to_lunar_date は現状 ephemeris 引数を受け取らない設計やから、
    #       ephemeris を効かせたい場合は build_range_cache / lunar_dates_between 経由で取るのが正攻法。
    #       ただし “六曜計算” 自体は ld から決まるので、ここはラッパとして最低限にしてる。
    return rokuyo_from_lunar_date(ld)


def fmt_with_rokuyo(g: date, ld: LunarDate) -> str:
    """
    test_kyureki.py の fmt を拡張する用途のユーティリティ。
    """
    leap = " (閏)" if ld.is_leap else ""
    r = rokuyo_r_from_lunar_month_day(ld.month, ld.day)
    label = rokuyo_from_lunar_month_day(ld.month, ld.day)
    return f"{g.isoformat()}  L={ld.month:02d}/{ld.day:02d}{leap}  R={r} {label}"