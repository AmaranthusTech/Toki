# ShinToki

旧暦計算プロジェクト（ShinToki）の Python ライブラリ + CLI です。  
公開用途では `shintoki.public` のAPIを安定面として扱い、`debug-*` は検証用として維持します。

## Compatibility Policy

- `shintoki.public` は互換維持対象です（シグネチャ/戻り型の破壊変更はメジャー変更扱い）。
- `debug-*` CLI とそのJSONは開発者向けです。検証用途のため、必要に応じて変更される可能性があります。
- 現在の公開版は `0.2.0` で、タグは `v0.2.0` 形式を推奨します。

## Setup (pip + venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
# jcal 比較機能も使う場合:
pip install -e ".[dev,compare]"
# HTTP API も使う場合:
pip install -e ".[dev,api]"
```

または:

```bash
make venv
source .venv/bin/activate
```

jcal 比較と 2033 修正パッチを含めた開発セットアップ:

```bash
make setup-online
source .venv/bin/activate
```

`make setup` は `make setup-online` のエイリアスです。`.[dev,compare]` の解決時にネットワーク接続が必要です。

ネットワークなし環境では:

```bash
make setup-offline
```

`setup-offline` は、既存 `.venv` と依存が入っている前提で patch 適用と最小検証（doctor / pytest / repro）を実行します。
`apply_patches.sh` は適用後に `lunisolar.py` 内の識別子を検査し、未適用なら失敗します。

短時間で最小確認だけ行う場合:

```bash
OFFLINE_VERIFY=0 make setup-offline
```

このモードでは `pytest` と `repro_jcal_2033.py` をスキップします。

`setup-online` 失敗時は以下を確認してください:
- `pip` の `--index-url` / `--extra-index-url` が使えるか（社内 mirror / private index）
- `HTTP_PROXY` / `HTTPS_PROXY` の設定
- `pip config` で mirror 設定（`pip config set global.index-url ...`）

`make` を使わずにパッチのみ適用する場合:

```bash
./scripts/apply_patches.sh
```

`apply_patches.sh` は marker `SHINTOKI_PATCH: JCAL_LUNISOLAR_V1` で適用確認を行います。
デフォルトで `.venv/bin/python` を自動使用し、必要なら `PYTHON=...` で上書きできます。

固定 patch を再生成する場合（`patches/jcal-lunisolar.patch` を更新）:

```bash
python scripts/make_clean_jcal_snapshot.py \
  --url https://github.com/AmaranthusTech/Toki.git \
  --commit f4789b4b42492a191da88eeb410bc10268c6e52a
```

ネットワークなし環境では `--from-file /path/to/clean/lunisolar.py` を使用してください。

## Doctor

ephemeris を指定して環境チェック:

```bash
python -m shintoki --format json doctor --ephemeris-path data/de440s.bsp
```

ephemeris 未指定時は `missing_ephemeris_path` エラーで終了します。

## debug-solstice

2033 年冬至相当の検証用コマンド（現在は未実装スタブ）:

```bash
python -m shintoki --format json debug-solstice \
  --year 2033 \
  --deg 270 \
  --tz Asia/Tokyo \
  --ephemeris-path data/de440s.bsp
```

## debug-spans

新月スパン（朔〜次朔）に中気イベント（30度刻み）を割り当て、`zero-zhongqi` と `zhongqi>=2` を確認:

```bash
python -m shintoki debug-spans --year 2033 --format json
python -m shintoki debug-spans --year 2033 --only-anomalies --format text
```

## debug-months

`debug-spans` の割当結果から month naming（11月アンカー + 閏月）を確認:

```bash
python -m shintoki debug-months --year 2033 --format json
python -m shintoki debug-months --year 2033 --window-mode solstice-to-solstice --format json
python -m shintoki debug-months --year 2033 --strict-expect-leap --format json
python -m shintoki debug-months --year 2033 --only-anomalies --format text
```

`--window-mode`:
- `calendar-year`（default）: 対象年に重なる span を抽出
- `solstice-to-solstice`: deg=270 span から次の deg=270 span 手前まで（12/13想定）
- `raw`: 正規化なし（strict期待が効かない場合あり）

## debug-compare

ShinToki の `debug-spans` / `debug-months` を同一条件でまとめ、必要なら jcal の 2033-06-10 再現情報も同じ JSON に添付:

```bash
python -m shintoki debug-compare --year 2033 --window-mode solstice-to-solstice --format json
```

`jcal` が無い環境でもコマンドは落ちず、`jcal.ok=false` とエラー情報を返します。

## Stable Python API

公開用の安定APIは `shintoki.public` です。

```python
from datetime import date
from shintoki.public import (
    gregorian_to_lunar,
    principal_terms_between,
    lunar_months_for_year,
)

print(gregorian_to_lunar(date(2017, 6, 9), tz="Asia/Tokyo"))
events = principal_terms_between(
    start_date=date(2017, 6, 1),
    end_date=date(2017, 7, 1),
    tz="Asia/Tokyo",
)
print(events[:1])
months = lunar_months_for_year(2033, tz="Asia/Tokyo")
print(months[:1])
```

互換のため `shintoki.api` は当面維持していますが、新規利用は `shintoki.public` を推奨します。

## Data Export / Validate CLI

配布用データ生成と検証:

```bash
python -m shintoki export-sqlite --start 2017-06-01 --end 2017-06-09 --tz Asia/Tokyo --out tmp/calendar.sqlite3
python -m shintoki export-jsonl  --start 2017-06-01 --end 2017-06-09 --tz Asia/Tokyo --out tmp/calendar.jsonl
python -m shintoki validate-sqlite --sqlite tmp/calendar.sqlite3 --samples 5 --tz Asia/Tokyo
```

Releases で SQLite/JSONL を配布する運用を想定しています（ephemeris本体は同梱しない方針）。
SQLite には `meta` テーブル（`schema_version`, `range_start`, `range_end`, `tz`, `window_mode`, `algo_version`, `ephemeris_name`, `ephemeris_sha256`, `generated_at`）を保持し、`validate-sqlite` で検証します。

`export-sqlite` は `--preset full-1900-2100` / `--preset lite-2000-2050` も利用できます。

### Release Asset Naming

配布ファイル名には `tz/window_mode/range/version` を必ず含めます。

- SQLite: `shintoki_{version}_{tz}_{window_mode}_{start}_{end}.sqlite3`
- JSONL: `shintoki_{version}_{tz}_{window_mode}_{start}_{end}.jsonl.gz`（非圧縮時は `.jsonl`）
- Checksum: `SHA256SUMS.txt`

例:
- `shintoki_v0.2.0_Asia-Tokyo_solstice-to-solstice_2000-01-01_2050-12-31.sqlite3`
- `shintoki_v0.2.0_Asia-Tokyo_solstice-to-solstice_2000-01-01_2050-12-31.jsonl.gz`

## HTTP API (Optional)

HTTP実行は別運用向けの最小実装です:

```bash
python -m shintoki api serve --host 127.0.0.1 --port 8010
```

## DB Reference API (for bloom)

配布済みSQLiteを参照する運用向けAPI:

```bash
python -m shintoki api-db serve --sqlite-path data/cache/shintoki.sqlite3 --host 127.0.0.1 --port 8011
```

DBパス解決順:
- `--sqlite-path`
- `SHINTOKI_DB_PATH`
- `./data/cache/shintoki.sqlite3`

- `GET /health`
- `GET /api/v1/day?date=YYYY-MM-DD&tz=Asia/Tokyo`
- `GET /api/v1/range?start=...&end=...&tz=Asia/Tokyo&strict=0|1`

欠損データ方針（A）:
- day miss: `404` + `{ok:false,error:{code:"not_found",missing:[...],hint:"precompute required"}}`
- range strict=1 で欠損あり: `404` + `missing`

## bloom Frontend Deploy (Static `index.html`)

同梱フロントは [web/index.html](/Users/approximate/project/ShinToki/web/index.html) です。  
`window.location.origin + "/Toki/api"` を基点に以下を呼び出します。

- `GET /Toki/api/v1/day?date=YYYY-MM-DD&tz=Asia/Tokyo`
- `GET /Toki/api/v1/range?start=YYYY-MM-DD&end=YYYY-MM-DD&tz=Asia/Tokyo&strict=0`

配置例:

```bash
install -m 0644 web/index.html /opt/homebrew/var/www/bloom/Toki/index.html
```

Nginx 前提（例）:
- `/Toki/index.html` を静的配信
- `/Toki/api/` を `http://127.0.0.1:8010/` に proxy

API動作確認（zsh 注意: URL は必ずシングルクォート）:

```bash
curl -s 'https://bloom.amaranthus.tech/Toki/api/v1/day?date=2026-03-05&tz=Asia/Tokyo' | jq
curl -s 'https://bloom.amaranthus.tech/Toki/api/v1/range?start=2026-03-05&end=2026-03-15&tz=Asia/Tokyo&strict=0' | jq
```

## Test

```bash
make test
```

## Lint / Format / Bench

```bash
make lint
make fmt
make bench
```
