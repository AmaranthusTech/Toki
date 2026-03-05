# SPEC.md — 旧暦/暦注 API & キャッシュ基盤（Toki）

## 目的
旧暦（lunisolar）、六曜（rokuyo）、二十四節気（sekki）などの暦注情報を、HTTP API として安定・高速に提供する。  
初回計算コストが高い範囲リクエストでも、事前生成（precompute）＋SQLiteキャッシュにより、実運用でのタイムアウトを防ぐ。

ShinToki本体では「ライブラリ + CLI + データ生成/検証」を主軸にし、HTTP運用は別プロジェクトへ分離可能な構成を維持する。

## スコープ
- API（FastAPI/uvicorn）
- ephemeris（de440s.bsp / de421.bsp）を用いた天文計算
- SQLite による日単位キャッシュ（read-through）
- 事前生成 CLI（precompute）と配布用 export（sqlite/jsonl）

## 非スコープ
- 計算ロジック（旧暦/節気計算）のアルゴリズム改変（※バグ修正は別途）
- UI（デモUI含む）の本格実装
- Cloudflare / CDN ルールの最適化（必要なら運用で対応）

## 想定ユースケース
1. UI が「単日/範囲」を指定して暦注を取得  
2. Cloudflare 経由で公開 API を叩く  
3. 本番前に年単位で precompute を回し、キャッシュ済みデータを配布（sqlite/jsonl）

## API 要件（基本）
### エンドポイント
- `/health`
  - 200 を返すこと（運用監視用）
  - 例: `{ ok, ephemeris_present, cache_db_path, cache_db_writable, cache_failures_count, error, api_version }`
- `/range`
  - `start`, `end`（YYYY-MM-DD）
  - `items`（複数指定可）: `lunisolar`, `rokuyo`, `sekki`, `moon_age`, `sunrise_sunset` など
  - `tz`（default Asia/Tokyo）, `lat/lon`（必要時）
  - レスポンスは requested start/end のみ返す（内部バッファは外に見せない）
  - `cache: { hits, misses, failures_count, failed_dates }` を含める

### 性能
- キャッシュヒット時: できるだけ短時間（数十〜数百ms）で応答
- 初回（キャッシュミス）での heavy compute を Cloudflare 経由で実行しない運用を推奨  
  → 事前に precompute で当該期間を温める

### 信頼性
- `/health` は例外で落ちない（運用で 500 を避ける）
- 日単位の計算失敗は failures として保存し、再試行ループを抑制
- strict モード（例 `strict=1`）では失敗時に全体を 500 扱いにできる

## キャッシュ仕様
### 保存単位
- 1日 + パラメータ（items/tz/lat/lon/ephemeris/version）でキーを作る
- 値は JSON（value_json）として保存

### ストレージ
- SQLite（WAL推奨）
- テーブル例:
  - `day_cache(key TEXT PRIMARY KEY, value_json TEXT NOT NULL, created_at INTEGER NOT NULL, version TEXT)`
  - `day_cache_failures(key TEXT PRIMARY KEY, created_at INTEGER NOT NULL, error_type TEXT NOT NULL, error_message TEXT NOT NULL)`

### 内部計算バッファ
- `TOKI_CACHE_BUFFER_DAYS`（default 120）を内部 range の start/end に ±付与
- `lunisolar` / `rokuyo` を含む場合は最小 240 日を強制（必要に応じて拡張）
- 「expand cache window」系のエラーは段階的にバッファ拡張してリトライする（例 240→320→400→500）

## CLI（precompute/export）
### precompute
- 期間を指定して、日単位キャッシュを作る
- 失敗は failures に記録しつつ継続（`--continue-on-error`）
- chunk でまとめて計算（1 chunk = N日）し、chunk 内の各日分を保存

例:
```bash
python -m demo_api.toki_cache precompute \
  --start 2026-02-01 --end 2026-03-31 \
  --items lunisolar --items rokuyo --items sekki \
  --tz Asia/Tokyo \
  --chunk-days 30 \
  --continue-on-error
```

### export
- `export-sqlite`: キャッシュDBを配布用にコピー（必要ならVACUUM）
- `export-json`: JSONL（1行=1日）を出力（欠損/失敗も任意で含める）

### debug-spans（検証用CLI）
- 目的: 新月スパン（朔〜次朔）に中気イベント（30度刻み）を割り当て、`zhongqi=0` と `zhongqi>=2` のスパンを可視化する
- 入力: `year`, `pad-days`, `degrees`, `tz`, `ephemeris-path`
- 出力(JSON): `search_window`, `spans`, `summary: { span_count, zeros, many }`
- 割当規則: `start_utc <= event_utc < end_utc`（UTC左閉右開）

### debug-months（検証用CLI）
- 目的: `debug-spans` の割当から month naming（11月アンカー）を最小実装で付与し、閏月候補を可視化する
- ルール: `deg=270` を含む span を month=11 の anchor にし、`zhongqi=0` の span は `is_leap=true`
- 月番号: 通常月のみ進め、閏月は同じ月番号を維持
- strictモード: `strict_expect_leap=true` で 12 span + zero-zhongqi を issue 化（例外は出さない）
- window正規化:
  - `raw`: 正規化なし
  - `calendar-year`: 対象年に重なる span のみ抽出
  - `solstice-to-solstice`: deg=270 span から次の deg=270 span の手前まで抽出（12/13想定）
- 出力(JSON): `months`, `summary: { anchor_span_index, anchor_term_utc, anchor_span_start_utc, anchor_span_end_utc, span_count_raw, span_count_normalized, window_mode, normalization_note, normalization_issues, leap_spans, zero_spans, months_count, issues }`

### debug-compare（切り分け用CLI）
- 目的: 同一入力条件で `debug-spans` と `debug-months` を比較しやすい JSON に統合し、必要なら jcal 側再現結果も添付する
- 出力(JSON): `{ year, tz, ephemeris_path, window_mode, pad_days, shintoki, jcal }`
- `shintoki`: `{ spans_summary, months_summary, months, spans, summary }`
- `jcal`: `gregorian_to_lunar(date(year,6,10))` を試行し、失敗時も `ok=false` とエラー情報を返す
- compare extras: `pip install -e ".[dev,compare]"` で jcal を導入して再現比較を有効化

## 安定公開API（ShinToki）
### Python API
- `shintoki.public.gregorian_to_lunar(date, tz="Asia/Tokyo", ephemeris_path=None, window_mode="solstice-to-solstice") -> LunarYMD`
- `shintoki.public.principal_terms_between(start_date, end_date, tz="Asia/Tokyo", degrees=[0..330 step30], ephemeris_path=None) -> list[TermEvent]`
- `shintoki.public.lunar_months_for_year(year, tz="Asia/Tokyo", window_mode="solstice-to-solstice", ephemeris_path=None) -> list[NamedMonth]`
- `shintoki.api.*` は後方互換レイヤとして当面維持（新規利用は `shintoki.public` 推奨）

### HTTP API（FastAPI）
- `GET /api/v1/day`
- `GET /api/v1/range`
- `python -m shintoki api serve` で起動
- `debug-*` 系CLIのJSONは検証用途であり、公開APIスキーマとは分離する

## データ生成/配布CLI
- `shintoki export-sqlite --start --end --tz --out`
  - 日次の旧暦/六曜/節気を `daily_calendar` テーブルへ保存
  - 主キー日付 + `(tz,d)` インデックスを作成
  - `meta` テーブルを固定スキーマで保持
- `shintoki export-jsonl --start --end --tz --out`
  - 1日1行JSONで保存
- `shintoki validate-sqlite --sqlite --samples --tz`
  - ランダムサンプルをライブラリ再計算と突合し、差分サマリを返す

### SQLite meta schema (schema_version=1)
- `schema_version`
- `range_start`
- `range_end`
- `tz`
- `window_mode`
- `algo_version`
- `ephemeris_name`
- `ephemeris_sha256`
- `generated_at`

`validate-sqlite` は上記キー存在と、`schema_version/tz/window_mode/ephemeris_*` の整合性を検証する。

## 受け入れ基準（Acceptance）
- `/health` が常に 200 を返す（ephemeris 未配置でも JSON で状態が分かる）
- precompute が指定期間で動作し、`day_cache` が増える
- キャッシュ済み期間に対して `/range` が高速（hits が増える）
- export が正常にファイルを生成できる

## 既知リスク
- 特定年（例: 2033 周辺）で旧暦計算が例外になる可能性  
  → failures に隔離し運用は継続できるが、根治は計算ロジックの検証・修正が必要
- 長期間 precompute は時間がかかるため、段階的に温める運用が現実的
