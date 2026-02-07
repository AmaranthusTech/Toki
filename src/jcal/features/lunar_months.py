# src/jcal/features/lunar_months.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

from jcal.core.month_naming import NamedLunarMonth
from jcal.features.config import lunar_month_display_name

@dataclass(frozen=True)
class FeatureLunarMonth:
    pos: int
    month_no: int
    is_leap: bool
    month_name: str
    new_moon_utc: datetime
    next_new_moon_utc: datetime
    zhongqi_deg: Optional[int]
    zhongqi_utc: Optional[datetime]

    @property
    def label(self) -> str:
        return self.month_name

def enrich_named_months(named: List[NamedLunarMonth]) -> List[FeatureLunarMonth]:
    out: List[FeatureLunarMonth] = []
    for m in named:
        out.append(
            FeatureLunarMonth(
                pos=m.pos,
                month_no=m.month_no,
                is_leap=m.is_leap,
                month_name=lunar_month_display_name(m.month_no, m.is_leap),
                new_moon_utc=m.new_moon_utc,
                next_new_moon_utc=m.next_new_moon_utc,
                zhongqi_deg=m.zhongqi_deg,
                zhongqi_utc=m.zhongqi_utc,
            )
        )
    return out