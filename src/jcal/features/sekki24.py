# src/jcal/features/sekki24.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List
from zoneinfo import ZoneInfo

from jcal.core.astronomy import AstronomyEngine
from jcal.core.config import SolarTermConfig
from jcal.core.solarterms import sekki24_between
from jcal.features.config import sekki_info_from_deg  # NEW: feature config を参照

JST = ZoneInfo("Asia/Tokyo")


def _require_utc(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Sekki24Event:
    """
    A single 24-sekki event (UTC instant + derived JST info).
    """
    deg: int        # normalized: 0,15,...,345
    n: int          # 0..23
    name: str
    kind: str       # "節" or "中気"
    utc: datetime
    jst: datetime
    jst_date: str   # YYYY-MM-DD


def sekki24_events_between(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    config: SolarTermConfig = SolarTermConfig(),
) -> List[Dict]:
    """
    24節気イベントを [start_utc, end_utc) の範囲で列挙する。

    - core.solarterms.sekki24_between は (deg, t_utc) を返す（degは15度刻み想定）
    - features.config.sekki_info_from_deg を使って:
        - deg の正規化（float誤差吸収）
        - n=0..23
        - name（日本語名）
        - kind（節/中気: n偶数=中気, 奇数=節）
      を一元的に決定する。

    Returns:
      list[dict] with keys:
        - deg, n, name, kind
        - utc (datetime), jst (datetime), jst_date (YYYY-MM-DD)
    """
    start_utc = _require_utc(start_utc, "start_utc")
    end_utc = _require_utc(end_utc, "end_utc")
    if not (start_utc < end_utc):
        raise ValueError("start_utc must be < end_utc")

    terms = sekki24_between(eng, start_utc, end_utc, config=config)

    out: List[Dict] = []
    for deg, t_utc in terms:
        t_utc = _require_utc(t_utc, "term_utc")

        # NEW: config側で正規化・n/kind/name を確定させる
        info = sekki_info_from_deg(float(deg))

        t_jst = t_utc.astimezone(JST)
        out.append(
            {
                "deg": int(info.deg),   # normalized int (0..345 step 15)
                "n": int(info.n),       # 0..23
                "name": info.name,
                "kind": info.kind,      # "節" / "中気"
                "utc": t_utc,
                "jst": t_jst,
                "jst_date": t_jst.date().isoformat(),
            }
        )

    out.sort(key=lambda x: x["utc"])
    return out


def sekki24_events_between_as_objects(
    eng: AstronomyEngine,
    start_utc: datetime,
    end_utc: datetime,
    *,
    config: SolarTermConfig = SolarTermConfig(),
) -> List[Sekki24Event]:
    """
    dict ではなく dataclass で欲しい場合の薄いラッパー。
    """
    rows = sekki24_events_between(eng, start_utc, end_utc, config=config)
    return [
        Sekki24Event(
            deg=int(r["deg"]),
            n=int(r["n"]),
            name=r["name"],
            kind=r["kind"],
            utc=r["utc"],
            jst=r["jst"],
            jst_date=r["jst_date"],
        )
        for r in rows
    ]