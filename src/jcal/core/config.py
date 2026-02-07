# src/jcal/core/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

LuniSolar2033Policy = Literal["auto", "leap11", "leap7", "leap12", "leap1"]

@dataclass(frozen=True)
class NewMoonConfig:
    scan_step_hours: int = 6
    newmoon_side_max_abs_deg: float = 90.0
    eps_sin: float = 1e-12

    tol_seconds: float = 0.5

    rebracket_window_hours: int = 36
    rebracket_scan_minutes: int = 30

    refine_window_minutes: int = 90
    refine_scan_minutes: int = 10
    refine_tol_seconds: float = 0.1

    merge_seconds: int = 24 * 3600

    polish_max_abs_deg: float = 5.0
    polish_bracket_minutes: int = 120


@dataclass(frozen=True)
class SolarTermConfig:
    """
    Configuration for solar longitude crossing searches (e.g., 24 sekki / solar terms).
    All time units are explicit to avoid minute/second confusion.
    """
    scan_step_hours: int = 6
    tol_seconds: float = 0.5
    merge_seconds: float = 60.0
    rebracket_window_hours: int = 2
    rebracket_step_minutes: int = 10


@dataclass(frozen=True)
class LuniSolarConfig:
    """
    Phase-2 luni-solar configuration.

    All inputs/outputs are UTC-based.
    """
    # New moon series padding (days)
    series_pad_days: int = 30

    # Principal-term (zhongqi) search padding (days)
    term_pad_days: int = 20

    # Search range around the target window for winter-solstice anchor (days)
    anchor_search_days: int = 200  # enough to include one solstice

    # Merge terms closer than this threshold (seconds)
    merge_seconds: float = 60.0

    # Window used when computing lunar day at a single instant.
    # We search new moons in [t - window, t + window].
    instant_window_days: int = 40
    
    # 旧暦2033年問題の扱い
    policy_2033: LuniSolar2033Policy = "leap11"


@dataclass(frozen=True)
class JCalConfig:
    newmoon: NewMoonConfig = field(default_factory=NewMoonConfig)
    solarterm: SolarTermConfig = field(default_factory=SolarTermConfig)
    lunisolar: LuniSolarConfig = field(default_factory=LuniSolarConfig)