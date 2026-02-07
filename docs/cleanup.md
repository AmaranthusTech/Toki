# Cleanup Report

This document records items removed for public release and the reasons.

## Removed (or to be removed)
- .venv/ — local virtual environment (large, machine-specific)
- data/*.bsp — ephemeris binaries (large; users must download separately)
- mnt/data/高精度計算サイト_2016_2034.txt — reference data with unclear redistribution rights
- sekki24_2016_2020.json — local/derived artifact
- *.log — local logs
- __pycache__/ and .pytest_cache/ — runtime caches
- .DS_Store — OS metadata

## Retained
- docs/public_api.md — stable API spec
- tests/test_public_api_calendar.py — reference-aligned tests (skip if ref not present)
- src/jcal/** — core implementation

## Notes
- Users must provide ephemeris via `TOKI_EPHEMERIS_PATH` or `./data/de440s.bsp`.
- Reference data is optional; tests will skip if not present.
