# Changelog

## 0.2.0 - 2026-02-27

- Added stable public API namespace: `shintoki.public`
  - `gregorian_to_lunar`
  - `principal_terms_between`
  - `lunar_months_for_year`
- Added data distribution CLI:
  - `export-sqlite`
  - `export-jsonl`
  - `validate-sqlite`
- Fixed stable API timezone handling for lunar month lookup.
- Added SQLite `meta` table for export artifacts:
  - `schema_version`
  - `tz`
  - `window_mode`
  - `algo_version`
  - `ephemeris_name`
  - `ephemeris_sha256`
  - `generated_at`
- Added validation of SQLite metadata in `validate-sqlite`.
- Kept existing `debug-*` command behavior and JSON compatibility.
