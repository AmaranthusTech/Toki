# TESTPLAN.md
旧暦計算プロジェクト（Toki / jcal系）のテスト計画書（Test Plan）です。  
目的は **(1) 正しさの担保** と **(2) 運用で落ちない堅牢性** と **(3) 体感速度の改善** を、段階的に確認できる形にすることです。

---

## 1. スコープ

### 対象
- コア計算（旧暦・六曜・節気・天文イベント等）
- API（FastAPI / Uvicorn）  
  - `/api/v1/range` / `/api/v1/day`
  - `/api/v1/calendar/range` / `/api/v1/calendar/day`
- Ephemeris（`de440s.bsp` / `de421.bsp`）読み込み
- キャッシュ（SQLite / 配布物 / JSONL）
- CLI（precompute / export）

### 非対象（当面）
- UI（デモ画面）そのもののE2E（必要なら後で追加）
- Cloudflare など外部CDN設定（挙動確認はするが、設定検証は運用側）

---

## 2. 品質目標（合格ライン）

### 正しさ
- 参照データと照合できる範囲（例：2016〜2034の節気/旧暦/六曜）で一致率が高いこと
- 既知の難所（閏月/冬至またぎ/朔またぎ）で破綻しないこと

### 可用性
- APIが **500連発しない**（strict=true時の意図的な500は除く）
- Ephemeris欠如時に「明確なエラー」を返す（沈黙してnull量産しない）

### 性能
- キャッシュwarm時のrangeが **十分高速**（例：60日レンジが数百ms〜数秒）
- precomputeが途中失敗しても **継続でき、失敗が可視化** される

---

## 3. テスト環境

### 必要ファイル
- `data/de440s.bsp`（推奨）または `data/de421.bsp`
- 参照データ（例：`高精度計算サイト_2016_2034.txt` など）

### 推奨コマンド（環境確認）
```bash
python -V
python -c "import fastapi, uvicorn; print('ok')"
ls -lah data/de440s.bsp data/de421.bsp 2>/dev/null || true
```

---

## 4. テスト種別と内容

## 4.1 ユニットテスト（コア）
### 目的
- 日付境界（JST日付切替）
- 朔（新月）計算の単体検証
- 節気（特に冬至=270°）の単体検証
- 閏月判定の単体検証

### 主要ケース
1) **冬至イベントの時刻が取得できる**
- 対象：`principal_terms_between` / それに相当するAPI内部ロジック
- 期待：2033年の冬至（deg=270）を含むレンジでイベントが返る

2) **朔（新月）イベント列が単調に並ぶ**
- 期待：時間順にソートされ、逆転がない

3) **月名付け（month_naming）に矛盾がない**
- 期待：閏月がある年は “中気ゼロの月がちょうど1つ” に近い挙動になる（仕様に合わせる）

4) **debug-spans で zero-zhongqi / many-zhongqi を検出できる**
- 期待：`summary.zeros` と `summary.many` が出力され、対象 span の境界時刻を追跡できる
- 境界条件：中気イベント時刻が span の end と一致する場合は次 span にのみ入る（UTC左閉右開）

5) **month naming（閏月含む）の最小実装が破綻しない**
- 期待：`deg=270` を含む span が month=11 の anchor になる
- 期待：`zhongqi=0` span が `is_leap=true` になり、月番号は据え置かれる
- 2033検証：`debug-spans.summary.zeros` と `debug-months.summary.leap_spans` が整合する
- strict検証：`debug-months --strict-expect-leap` で 12 span + zero の場合に `summary.issues` が出る（例外にはしない）
- window-mode 検証：`raw / calendar-year / solstice-to-solstice` で `span_count_normalized` が想定どおり変化し、strict判定は normalized spans 基準で行われる

6) **debug-compare で ShinToki と jcal の差分を同一JSONで比較できる**
- 期待：`shintoki.summary` に spans/months の比較キー（zeros, leap_spans, issues 等）が揃う
- 期待：jcal 未導入環境でも `jcal.ok=false` を返し、コマンド自体は成功する
- 期待：jcal 導入環境（`.[compare]`）では `jcal.error_type` が `ModuleNotFoundError` 以外になる

7) **公開API（Python/HTTP）の固定スキーマを維持できる**
- 対象: `shintoki.api.gregorian_to_lunar`, `principal_terms_between`, `/api/v1/day`, `/api/v1/range`
- 期待: 既存の debug-* JSON互換を壊さずに公開APIの戻り値キーが安定する
- 期待: Golden（最小）として 2017-06-09 の `day` 応答（旧暦/六曜/節気）を fixture と一致確認できる

8) **公開ライブラリAPI（shintoki.public）の互換維持**
- 対象: `gregorian_to_lunar`, `principal_terms_between`, `lunar_months_for_year`
- 期待: 型（LunarYMD/TermEvent/NamedMonth）と引数シグネチャが維持される
- 期待: `window_mode` 切替で month naming 取得が例外なく動作する

9) **export / validate CLI の整合性**
- `export-sqlite`: 指定期間の日数分レコードが保存される
- `export-sqlite`: `meta` テーブルに `schema_version/tz/window_mode/algo_version/ephemeris_*` が保存される
- `export-jsonl`: 指定期間の日数分の行数が出力される
- `validate-sqlite`: ランダムサンプル比較で `mismatch_count` が確認でき、差分詳細が出る
- `validate-sqlite`: `meta` 不整合（tz/window_mode/schema_version/sha256）を検知できる
- 既存 `debug-*` の JSON スキーマ互換を壊さない

---

## 4.2 ユニットテスト（APIハンドラ）
### 目的
- バリデーション（start/end、limit_days、tz、lat/lon）
- strictモードの挙動（導入している場合）
- エラーがJSONで返ること（/health含む）

### 主要ケース
- 正常：短いrange（例：3日）で200 + JSON
- 異常：end < start → 400/422
- 異常：limit_days超過 → 400/422
- 異常：ephemeris欠如 → 500 ではなく明確なエラー（仕様に従う）

---

## 4.3 参照データ照合（リグレッション）
### 目的
- “正しいっぽい” ではなく、外部参照と突き合わせて継続的に品質を測る

### 実施例
- 2017年の閏月を含むレンジ（既知のテスト）
- 2016〜2034の節気日付一致（日付単位）
- 旧暦・六曜の一致  
（既存の `tests/compare_sekki_greg_range.py` のようなスクリプトを継続利用）

---

## 4.4 性能テスト（ローカル）
### 目的
- “遅い” を定量化し、改善が効いたか比較できるようにする

### 指標
- cold（キャッシュ無し）: 1日 / 30日 / 90日
- warm（キャッシュ有り）: 同上
- precompute速度: 秒/日、chunk-days別の比較

### 例（計測）
```bash
time curl -sG "http://127.0.0.1:8010/api/v1/range"   --data-urlencode "start=2026-02-01"   --data-urlencode "end=2026-03-31"   --data-urlencode "tz=Asia/Tokyo" >/dev/null
```

---

## 4.5 耐久テスト（失敗隔離/継続）
### 目的
- 一部日付がコケても全体が止まらない（または strict=trueなら止める）を確認

### 主要ケース
- precomputeで `--continue-on-error` が効く
- failuresログ/DBに保存される（設計がある場合）
- export-json / export-sqlite が落ちない

---

## 5. 重点バグ・再現ケース（既知の難所）

## 5.1 2033-06 近辺
- 再現：`gregorian_to_lunar(date(2033,6,10))` 等で例外が出るケースがある
- ここは **回避（許容ロジック） or 根治（境界/閏判定修正）** の判断が必要
- テストとしては以下を用意する：
  - strict=false：APIがnull返却＋ログに原因（またはerror構造）  
  - strict=true：500 + detailで原因を返す  
  - コア単体：例外が出るなら “既知失敗” として明確に記録（将来fixで更新）

---

## 6. 実行手順（テストの回し方）

### 6.1 まず最小の動作確認
1. ephemeris配置
2. uvicorn起動
3. `/openapi.json` でルート確認
4. `/api/v1/range` で200確認

### 6.2 回帰テスト
- 参照データ照合スクリプトを実行  
- 既知の “合格する年（2017等）” をまず通す

### 6.3 性能テスト
- cold → warm の比較
- chunk-days を変えて precompute速度測定

---

## 7. 成果物（ログ/レポート）

テスト実行ごとに残すもの：
- 実行コマンドと結果（stdout）
- 主要レンジのレスポンスサンプル（短縮でもOK）
- 例外スタック（strict=trueで取得）
- 性能結果（time/cProfile等）

---

## 8. 次のアクション（おすすめ順）

1) **2033-06 を「仕様としてどう扱うか」決める**（strict/許容/根治）
2) “冬至(270°)” のイベント時刻取得テスト（単体）を追加し、回帰を作る
3) precompute / export のE2EをCIで回せる最小セットを用意
4) 長期（1900-2100）の完走テストは “夜間・手動 or 分割ジョブ” にして現実運用に寄せる

---

## 付録：ワンライナー集

### 2033-06 の再現（コア直叩き）
```bash
PYTHONPATH=src python - <<'PY'
from datetime import date
from jcal.core.lunisolar import gregorian_to_lunar
print(gregorian_to_lunar(date(2033,6,10)))
PY
```

### デバッグ窓（lunisolar）
```bash
export JCAL_DEBUG_LUNISOLAR=1
export JCAL_DEBUG_FROM=2033-06-01
export JCAL_DEBUG_TO=2033-07-01
```

### API: range
```bash
curl -sG "http://127.0.0.1:8010/api/v1/range"   --data-urlencode "start=2033-06-10"   --data-urlencode "end=2033-06-20"   --data-urlencode "tz=Asia/Tokyo"
```
