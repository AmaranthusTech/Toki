from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from shintoki.api.public import day_calendar


def _diff_paths(actual, expected, prefix: str = "") -> list[str]:
    diffs: list[str] = []
    if type(actual) is not type(expected):
        diffs.append(f"{prefix}: type {type(actual).__name__} != {type(expected).__name__}")
        return diffs
    if isinstance(actual, dict):
        keys = sorted(set(actual) | set(expected))
        for key in keys:
            path = f"{prefix}.{key}" if prefix else key
            if key not in actual:
                diffs.append(f"{path}: missing in actual")
                continue
            if key not in expected:
                diffs.append(f"{path}: unexpected in actual")
                continue
            diffs.extend(_diff_paths(actual[key], expected[key], path))
        return diffs
    if isinstance(actual, list):
        if len(actual) != len(expected):
            diffs.append(f"{prefix}: len {len(actual)} != {len(expected)}")
            return diffs
        for idx, (lhs, rhs) in enumerate(zip(actual, expected)):
            diffs.extend(_diff_paths(lhs, rhs, f"{prefix}[{idx}]"))
        return diffs
    if actual != expected:
        diffs.append(f"{prefix}: {actual!r} != {expected!r}")
    return diffs


@pytest.mark.skipif(not Path("data/de440s.bsp").exists(), reason="requires data/de440s.bsp")
def test_day_golden_2017_06_09_matches_fixture() -> None:
    fixture = Path("tests/fixtures/golden_day_2017-06-09.json")
    expected = json.loads(fixture.read_text(encoding="utf-8"))

    actual = day_calendar(
        date(2017, 6, 9),
        tz="Asia/Tokyo",
        ephemeris_path="data/de440s.bsp",
    )
    diffs = _diff_paths(actual, expected)
    assert not diffs, "golden mismatch:\n" + "\n".join(diffs)
