# src/jcal/core/timeutil.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def require_utc(dt: datetime, name: str = "dt") -> datetime:
    """
    Ensure a datetime is timezone-aware and UTC.

    Parameters
    ----------
    dt:
        datetime to validate.
    name:
        Parameter name for error messages.

    Returns
    -------
    datetime
        The same datetime if valid.

    Raises
    ------
    ValueError
        If dt is naive or not UTC.
    """
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC datetime (got naive datetime)")
    off = dt.utcoffset()
    if off is None:
        raise ValueError(f"{name} has invalid tzinfo (utcoffset is None): {dt.tzinfo!r}")
    if off != timedelta(0):
        raise ValueError(f"{name} must be UTC (utcoffset=0). Got: {dt.tzinfo!r}")
    return dt


def require_utc_range(start_utc: datetime, end_utc: datetime) -> tuple[datetime, datetime]:
    """
    Validate [start_utc, end_utc] as UTC and ensure end_utc > start_utc.
    """
    start_utc = require_utc(start_utc, "start_utc")
    end_utc = require_utc(end_utc, "end_utc")
    if end_utc <= start_utc:
        raise ValueError("end_utc must be greater than start_utc")
    return start_utc, end_utc