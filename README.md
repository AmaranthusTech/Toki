# Toki

**Toki** is a FastAPI-based calendar API that returns Japanese lunisolar data
(旧暦/六曜/24節気/月齢など) as JSON, using **JST日付境界** as the authoritative day-basis.

> Package name remains `jcal` (internal module), but the public project name is **Toki**.

[![CI](https://github.com/AmaranthusTech/Toki/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AmaranthusTech/Toki/actions/workflows/ci.yml)

## Features
- 旧暦（閏月ラベル含む）
- 六曜
- 24節気（JST日付帰属）
- 月齢・新月イベント（最小）
- 日の出/日の入り（観測地点依存、デフォルト東京、lat/lon指定可）

## Dependencies
- fastapi>=0.110
- uvicorn[standard]>=0.23
- skyfield>=1.45
- numpy>=1.26

### Dev dependencies
- pytest>=7.0

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Optional (dev)
pip install -e ".[dev]"

uvicorn jcal.api.app:app --reload --app-dir src
```

## API Endpoints
- `GET /api/v1/calendar/day?date=YYYY-MM-DD`
- `GET /api/v1/calendar/range?start=YYYY-MM-DD&end=YYYY-MM-DD`

日の出/日の入りは観測地点に依存します。省略時は **東京駅付近**（lat=35.681236, lon=139.767125）。
任意で `lat` / `lon` をクエリに指定できます（例: `&lat=35.681236&lon=139.767125`）。

### Example (day)
```bash
curl -sS 'http://127.0.0.1:8000/api/v1/calendar/day?date=2017-06-24&day_basis=jst' \
  -H 'accept: application/json' | python -m json.tool
```

### Example Response (minimum)
```json
{
	"date": "2017-06-24",
	"lunisolar": {"year": 2017, "month": 5, "day": 1, "leap": true, "label": "閏05/01", "month_name": "閏五月"},
	"rokuyo": "大安",
	"sekki": null,
	"astronomy": {"moon_age": 0.0, "phase_event": {"type": "new_moon"}}
}
```

## Ephemeris (必須)
このリポジトリには **.bsp**（de440s.bsp など）を同梱しません。
NASA/JPL NAIF 公式配布から取得してください。

公式配布ディレクトリ:
https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/

macOS/Linux（wget）:
```bash
mkdir -p data
wget -O data/de440s.bsp https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp
```

macOS/Linux（curl）:
```bash
mkdir -p data
curl -L -o data/de440s.bsp https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp
```

`de421.bsp` にも対応していますが、**推奨しません**（古く精度が低いため）。

### 推奨配置
- `./data/de440s.bsp`

### 環境変数
```
TOKI_EPHEMERIS=de440s.bsp
TOKI_EPHEMERIS_PATH=/absolute/path/to/de440s.bsp
```
未指定の場合は `data/de440s.bsp` を優先して探します。
便利コマンド（毎回exportが面倒な場合）:
```bash
export TOKI_EPHEMERIS_PATH="$(pwd)/data/de440s.bsp"
```

direnv 例（任意）:
```bash
echo 'export TOKI_EPHEMERIS_PATH="'"$(pwd)"'/data/de440s.bsp"' > .envrc
direnv allow
```
優先順位:
1. APIクエリ `ephemeris_path`
2. 環境変数 `TOKI_EPHEMERIS_PATH`
3. APIクエリ `ephemeris`
4. 環境変数 `TOKI_EPHEMERIS`
5. デフォルト `de440s.bsp`

## Tools (単体検証スクリプト)
**必ず** `python -m tools.xxx` で実行してください。
`python tools/sekki24_check.py` のような実行は import の都合で落ちる可能性があります。

ephemeris が無い場合は **SKIP** を表示して終了します（終了コード0）。

```bash
python -m tools.sekki24_check --start 2017-06-01 --end 2017-06-30
python -m tools.lunisolar_check --date 2017-06-24
python -m tools.rokuyo_check --date 2017-06-24
```

ephemeris の指定:
```bash
TOKI_EPHEMERIS_PATH=/path/to/de440s.bsp python -m tools.lunisolar_check --date 2017-06-24
python -m tools.lunisolar_check --date 2017-06-24 --ephemeris-path /path/to/de440s.bsp
```

## Quick Verification Flow
1) venv 作成/有効化
2) `pip install -e .`（必要なら `pip install -e ".[dev]"`）
3) `data/de440s.bsp` を配置
4) `export TOKI_EPHEMERIS_PATH="$(pwd)/data/de440s.bsp"`
5) `python -m tools.sekki24_check --start 2017-06-01 --end 2017-06-30`
6) `uvicorn jcal.api.app:app --reload --app-dir src`
7) `curl -sS 'http://127.0.0.1:8000/api/v1/calendar/day?date=2017-06-24&day_basis=jst'`

## Tests
```bash
pytest -q
```
参照データ `高精度計算サイト_2016_2034.txt` がない場合は該当テストがスキップされます。

## Documentation
- [Public API spec](docs/public_api.md)
- Examples: docs/examples.md
- Cleanup notes (what’s excluded from release): docs/cleanup.md
  
## Development Notes
- 日付帰属は **JST日付境界** を正とする（UTC基準に戻さない）。

## License
MIT








